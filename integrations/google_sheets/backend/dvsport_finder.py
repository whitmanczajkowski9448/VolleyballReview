"""Browse authorized DV Sport FULL GAME matches and import individual plays.

Uses the existing services.dvsport_sync parser, including all camera angles.
Imports have no grades. If the play already exists, only DV Sport source
metadata/video URLs are enriched; no review fields or comments are changed.
"""
from datetime import date
import hashlib
import re
import threading
import time
from fastapi import HTTPException
from services import dvsport_sync as dv

_CACHE_LOCK = threading.RLock()
_LIBRARY = {"expires": 0.0, "groups": {}}
_PLAYLISTS = {}
TTL = 900


def match_id(conference, when, name):
    key = "|".join((dv.normalize_identity_text(conference),
                    str(when), dv.normalize_identity_text(name)))
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def group_full_games(items):
    groups = {}
    for item in items:
        path = dv.clean_text(item.get("Id"))
        url = dv.clean_text(item.get("Url"))
        if item.get("Type") != 0 or not url.upper().endswith(".DVPLAYLIST"):
            continue
        m = re.search(r"/VIDEOS/([0-9]{4})/([^/]+)/GAMES/", path, re.I)
        if not m:
            continue
        parsed = dv.parse_full_game_playlist_title(item.get("Title"))
        when, name = parsed.get("date"), dv.clean_text(parsed.get("match"))
        if not when or not name:
            continue
        conf = m.group(2).replace("_", " ").strip().upper()
        mid = match_id(conf, when.isoformat(), name)
        group = groups.setdefault(mid, {
            "match_id": mid, "conference": conf,
            "match_date": when.isoformat(), "match_name": name, "items": []})
        group["items"].append(item)
    for group in groups.values():
        group["items"].sort(
            key=lambda it: (dv.to_int(it.get("LastModifiedTicks")) or 0,
                            dv.to_int(it.get("NumberOfPlays")) or -1),
            reverse=True)
    return groups


def catalog(cookie):
    if not cookie:
        raise HTTPException(503, "DV Sport server cookie is not configured")
    with _CACHE_LOCK:
        if time.monotonic() < _LIBRARY["expires"]:
            return _LIBRARY["groups"]
    try:
        session = dv.make_session(cookie)
        items = dv.discover_library(session, dv.get_library_page(session, 1))
        groups = group_full_games(items)
    except Exception as exc:
        raise HTTPException(502, "Could not access authorized DV Sport library") from exc
    with _CACHE_LOCK:
        _LIBRARY.update(expires=time.monotonic()+TTL, groups=groups)
    return groups


def search_matches(cookie, start: date, end: date, conference="", search=""):
    if start > end or (end-start).days > 92:
        raise HTTPException(422, "Choose a date range of at most 92 days")
    q, conf = search.strip().casefold(), conference.strip().casefold()
    out = []
    for group in catalog(cookie).values():
        if not start.isoformat() <= group["match_date"] <= end.isoformat():
            continue
        if conf and group["conference"].casefold() != conf:
            continue
        if q and q not in group["match_name"].casefold():
            continue
        out.append({
            "match_id": group["match_id"],
            "conference": group["conference"],
            "match_date": group["match_date"],
            "match_name": group["match_name"],
            "play_count_hint": max((dv.to_int(x.get("NumberOfPlays")) or 0 for x in group["items"]), default=0)})
    out.sort(key=lambda x: (x["match_date"],x["conference"],x["match_name"]),reverse=True)
    return {"matches":out[:300],"total":len(out),"truncated":len(out)>300,
            "conferences":sorted({x["conference"] for x in out})}


def _match(cookie, mid):
    entry = catalog(cookie).get(mid)
    if not entry:
        raise HTTPException(404, "Match not found in your DV Sport library")
    return entry


def _plays(cookie, group):
    session = dv.make_session(cookie)
    combined = {}
    for item in group["items"][:3]:
        url = dv.clean_text(item.get("Url"))
        with _CACHE_LOCK:
            saved = _PLAYLISTS.get(url)
        if saved and saved[0] > time.monotonic():
            index = saved[1]
        else:
            try:
                index = dv._full_game_play_index(session, item, {}, {})
            except Exception as exc:
                if combined:
                    continue
                raise HTTPException(502, "Failed to load FULL GAME play data") from exc
            with _CACHE_LOCK:
                _PLAYLISTS[url] = (time.monotonic()+TTL, index)
        for num, value in index.items():
            if num not in combined:
                combined[num] = {"angles":value.get("angles") or [],
                                 "metadata":value.get("metadata") or {}, "source":url}
            else:
                combined[num]["angles"] = dv.merge_video_urls(
                    combined[num]["angles"], value.get("angles"))
    return combined


def _brief(number, play):
    f=play.get("metadata",{}).get("fields") or {}
    home,away=dv.clean_text(f.get("Home")),dv.clean_text(f.get("Away"))
    return {"play_number":int(number) if number.isdecimal() else number,
            "set_number":dv.to_int(f.get("SET")),
            "score":f"{home}-{away}" if home or away else "",
            "angle_count":len(play.get("angles") or []),
            "has_video":bool(play.get("angles"))}


def plays_in_match(cookie, mid):
    match=_match(cookie,mid)
    plays=_plays(cookie,match)
    def order(x): return (0,int(x)) if x.isdecimal() else (1,x)
    return {"match":{k:v for k,v in match.items() if k!="items"},
            "plays":[_brief(n,plays[n]) for n in sorted(plays,key=order)]}


def _find_existing(db, match, number):
    # A numbered play already flagged as Challenge/POI/Fault must never be
    # duplicated or reclassified as Saved.
    exact=(db.table("plays").select("*")
           .eq("conference",match["conference"])
           .eq("match_date",match["match_date"])
           .eq("dvsport_play_number",number)
           .limit(100).execute()).data or []
    target=dv.normalize_match_lookup_name(match["match_name"])
    for row in exact:
        if dv.normalize_match_lookup_name(row.get("match_name")) == target:
            return row
    # Legacy imports sometimes stored the play number in JSON only.
    old=(db.table("plays").select("*")
         .eq("conference",match["conference"]).eq("match_date",match["match_date"])
         .limit(500).execute()).data or []
    for row in old:
        if dv.normalize_match_lookup_name(row.get("match_name"))!=target:
            continue
        meta=row.get("dvsport_metadata") or {}
        num=row.get("dvsport_play_number") or (meta.get("full_game") or {}).get("play_number")
        if str(num or "")==str(number):
            return row
    return None


def import_play(db, cookie, mid, number):
    if number < 1:
        raise HTTPException(422, "Choose a positive DV Sport play number")
    match=_match(cookie,mid)
    found=_plays(cookie,match)
    play=found.get(str(number))
    if not play:
        raise HTTPException(404, "Selected PLAY number does not exist")
    angles=play.get("angles") or []
    if not angles:
        raise HTTPException(409, "DV Sport supplies no video angles for that play")
    metadata=play.get("metadata") or {}
    fields=metadata.get("fields") or {}
    home,away=dv.clean_text(fields.get("Home")),dv.clean_text(fields.get("Away"))
    patchmeta={"full_game":metadata,
               "full_game_lookup":{"status":"matched","play_number":str(number)},
               "manual_import":{"source":"Google Sheets","match_id":mid}}
    existing=_find_existing(db,match,number)
    if existing:
        # Do not write/erase any grade, category, reviewer note, or comment.
        merged=dv.merge_video_urls(existing.get("video_urls"),angles)
        patch={"video_urls":merged,
               "dvsport_metadata":dv.merge_dvsport_metadata(existing.get("dvsport_metadata"),patchmeta),
               "dvsport_full_game_url":play["source"]}
        db.table("plays").update(patch).eq("id",existing["id"]).execute()
        return {"status":"existing","play_id":str(existing["id"]),
                "play_type":existing.get("play_type"),"angle_count":len(merged)}
    identity="saved:v1:"+hashlib.sha256(f"{mid}|{number}".encode()).hexdigest()[:24]
    record={
        "dvsport_id":identity,"conference":match["conference"],
        "match_date":match["match_date"],"match_name":match["match_name"],
        "play_type":"Saved","set_number":dv.to_int(fields.get("SET")),
        "score":f"{home}-{away}" if home or away else None,
        "dvsport_play_number":number,"dvsport_full_game_url":play["source"],
        "dvsport_metadata":patchmeta,"video_urls":angles[:30]}
    # dvSport_id must be unique in Supabase for idempotent imports.
    rows=(db.table("plays").upsert(record,on_conflict="dvsport_id").execute()).data or []
    if not rows:
        raise HTTPException(502, "Database did not return saved play")
    return {"status":"imported","play_id":str(rows[0]["id"]),
            "play_type":"Saved","angle_count":len(angles)}
