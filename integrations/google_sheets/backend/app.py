"""VolleyReview integration API. Secrets stay on this server, never in the sheet."""
from __future__ import annotations

import ipaddress
import os
import re
import secrets
import socket
import threading
import time
import tempfile
import zipfile
from functools import lru_cache
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from supabase import Client, create_client
from dvsport_finder import search_matches, plays_in_match, import_play

from logic import (
    clean, compact_metadata, info_text, parse_angles, sign_download, valid_download_token, zip_name,
)

app = FastAPI(title="VolleyReview Sheets Integration", version="1.0")


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@lru_cache(maxsize=1)
def client() -> Client:
    url = setting("SUPABASE_URL")
    key = setting("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def require_api_key(x_integration_key: str | None = Header(default=None)) -> None:
    expected = setting("SHEETS_INTEGRATION_KEY")
    if not expected or not x_integration_key or not secrets.compare_digest(x_integration_key, expected):
        raise HTTPException(401, "Invalid integration credentials")


def public_url() -> str:
    url = setting("PUBLIC_BASE_URL").rstrip("/")
    if not url.startswith("https://"):
        raise HTTPException(503, "PUBLIC_BASE_URL must be configured with HTTPS")
    return url


def signing_secret() -> str:
    s = setting("DOWNLOAD_SIGNING_SECRET")
    if len(s) < 24:
        raise HTTPException(503, "DOWNLOAD_SIGNING_SECRET is not configured")
    return s


def get_play(play_id: str) -> dict:
    res = client().table("plays").select("*").eq("id", play_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "Play not found")
    return res.data[0]


# This app stores stable DV Sport media URLs in plays.video_urls. Like
# services/dvsport_media.py, we refresh Azure SAS links through FilmRoom.
# Backend deployments do not run Streamlit, so credentials come from env vars.
_sas_cache: dict[str, tuple[float, str]] = {}
_sas_lock = threading.Lock()


def refresh_media_url(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not (host.endswith(".blob.core.windows.net") and
            ("dvsport" in url.lower() or "wvb-clips" in url.lower())):
        return url
    cookie = setting("DVSPORT_COOKIE")
    if not cookie:
        return url  # if already signed, it may still work; README explains setup
    source = urlunsplit((parts.scheme, parts.netloc, unquote(parts.path), "", ""))
    now = time.monotonic()
    with _sas_lock:
        saved = _sas_cache.get(source)
        if saved and saved[0] > now:
            return saved[1]
    response = requests.post(
        "https://filmroom.dvsport360.com/VideoPlayer/GetSasUrl",
        data={"url": source},
        headers={"Origin": "https://filmroom.dvsport360.com",
                 "Referer": "https://filmroom.dvsport360.com/",
                 "X-Requested-With": "XMLHttpRequest",
                 "User-Agent": "Mozilla/5.0",
                 "Cookie": cookie},
        timeout=(10, 35), allow_redirects=False,
    )
    response.raise_for_status()
    data = response.json()
    signed = clean(data.get("Url") or data.get("url"))
    if not data.get("Success") or not signed:
        raise ValueError("DV Sport did not return a signed media URL")
    # A new signer must not be allowed to direct our downloader to an arbitrary host.
    approved_video_host(signed)
    with _sas_lock:
        _sas_cache[source] = (now + 20 * 60, signed)
    return signed


def get_angles(play: dict, *, refresh: bool = False) -> list[dict]:
    angles = parse_angles(play.get("video_urls"))
    if not angles:
        # Compatibility with older pre-video_urls installations.
        try:
            rows = (client().table("video_angles").select("angle_name,video_url")
                    .eq("play_id", play["id"]).order("id").limit(30).execute()).data or []
            angles = parse_angles(rows)
        except Exception:
            return []
    # Keep play-library listing fast. Refresh DV Sport SAS URLs only when a video is opened
    # or a ZIP is being generated; refreshing every angle for 4,000 plays takes hours.
    if not refresh:
        return angles
    updated = []
    for angle in angles:
        try:
            url = refresh_media_url(angle["url"])
        except (requests.RequestException, ValueError):
            url = angle["url"]
        updated.append({**angle, "url": url})
    return updated


def get_comments_for_play(play_id: str) -> list[dict]:
    # Comments are in a separate table to preserve the full history.
    res = (client().table("play_comments").select("id,play_id,author,comment_text,tags,source,created_at")
           .eq("play_id", play_id).order("created_at", desc=False).limit(1000).execute())
    return res.data or []


@app.get("/health")
def health():
    return {"status": "ok", "service": "VolleyReview Sheets API"}


@app.get("/api/v1/plays", dependencies=[Depends(require_api_key)])
def list_plays(offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=500)):
    res = (client().table("plays").select("*")
           .order("match_date", desc=True).order("id", desc=True)
           .range(offset, offset + limit).execute())
    rows = res.data or []
    output = []
    base = public_url()
    secret = signing_secret()
    days = min(max(int(setting("DOWNLOAD_LINK_TTL_DAYS", "14")), 1), 30)
    for row in rows[:limit]:
        metadata = compact_metadata(
            row, get_angles(row), base, secret, days,
            setting("VOLLEYREVIEW_PLAY_URL_TEMPLATE"),
        )
        # Provide signed, on-demand video links alongside the signed ZIP link.
        # Raw Azure blob URLs may require a short-lived DV Sport SAS signature.
        expires = int(time.time()) + days * 86400
        token = sign_download(str(row["id"]), expires, secret)
        play_id = quote(str(row["id"]), safe="")
        for index, angle in enumerate(metadata["angles"]):
            # Keep the original DV Sport source for direct Google Apps Script ZIP exports.
            # The visible watch URL remains the authenticated proxy link.
            angle["source_url"] = angle["url"]
            angle["url"] = (f"{base}/api/v1/plays/{play_id}/angles/{index}/watch"
                            f"?expires={expires}&sig={token}")
        output.append(metadata)
    return {
        "plays": output,
        "next_offset": offset + limit if len(rows) > limit else None,
    }


@app.get("/api/v1/comments", dependencies=[Depends(require_api_key)])
def list_comments(offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=500)):
    rows = (client().table("play_comments")
            .select("id,play_id,author,comment_text,tags,source,created_at")
            .order("created_at", desc=True).order("id", desc=True)
            .range(offset, offset + limit).execute()).data or []
    return {"comments": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}


class NewComment(BaseModel):
    comment_text: str = Field(min_length=1, max_length=4000)
    author: str = Field(default="Google Sheets reviewer", max_length=200)
    source: str = Field(default="Google Sheets", max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=15)


@app.post("/api/v1/plays/{play_id}/comments", dependencies=[Depends(require_api_key)])
def add_comment(play_id: str, payload: NewComment):
    get_play(play_id)  # verify play exists, and return a clear 404 instead of FK error
    msg = payload.comment_text.strip()
    if not msg:
        raise HTTPException(422, "Comment cannot be blank")
    tags = list(dict.fromkeys(
        re.sub(r"[^a-zA-Z0-9_ -]", "", clean(x))[:40]
        for x in payload.tags + re.findall(r"(?<!\w)#([A-Za-z][\w-]{1,39})", msg)
    ))
    tags = [x for x in tags if x][:15]
    new_row = {
        "play_id": play_id, "comment_text": msg, "author": payload.author.strip() or "Google Sheets reviewer",
        "tags": tags, "source": payload.source.strip() or "Google Sheets",
    }
    result = client().table("play_comments").insert(new_row).execute()
    if not result.data:
        raise HTTPException(500, "No comment returned after save")
    return result.data[0]


def approved_video_host(url: str) -> None:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    allow = [x.strip().lower().rstrip(".") for x in setting("ALLOWED_MEDIA_HOSTS").split(",") if x.strip()]
    if parsed.scheme != "https" or not hostname or not allow:
        raise ValueError("Video URL is not HTTPS or ALLOWED_MEDIA_HOSTS is not configured")
    if not any(hostname == h or hostname.endswith("." + h) for h in allow):
        raise ValueError(f"Video host is not on allowlist: {hostname}")
    # Refuse local/private targets before making a server-side request.
    for _family, _socktype, _proto, _canon, sockaddr in socket.getaddrinfo(hostname, 443):
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            raise ValueError("Non-public video destination is blocked")


def open_media_url(session: requests.Session, url: str) -> requests.Response:
    current = url
    for _ in range(6):
        approved_video_host(current)
        response = session.get(current, allow_redirects=False, timeout=(10, 90), stream=True,
                               headers={"User-Agent": "VolleyReviewSheets/1.0"})
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            response.close()
            if not location:
                raise ValueError("Media redirect lacks Location")
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise ValueError(f"Media HTTP {status}")
        ctype = response.headers.get("Content-Type", "").lower()
        if any(x in ctype for x in ("text/html", "application/json", "mpegurl")) or urlsplit(current).path.lower().endswith(".m3u8"):
            response.close()
            raise ValueError("Not a downloadable video file (HLS playlists require MP4 conversion)")
        return response
    raise ValueError("Too many video redirects")


def cleanup_file(path: str):
    Path(path).unlink(missing_ok=True)


def make_zip(play: dict, angles: list[dict], comments: list[dict]) -> str:
    max_total_bytes = max(1, int(setting("MAX_ZIP_TOTAL_MB", "1500"))) * 1024 * 1024
    fd, path = tempfile.mkstemp(suffix=".zip", prefix="volleyreview_")
    os.close(fd)
    total = 0
    success = 0
    failures = []
    used_names: set[str] = set()
    with requests.Session() as session:
        try:
            with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                archive.writestr("Play_Information.txt", info_text(play, angles, comments))
                for i, angle in enumerate(angles, 1):
                    try:
                        with open_media_url(session, angle["url"]) as response:
                            ext = Path(urlsplit(response.url).path).suffix.lower()
                            if ext not in (".mp4", ".mov", ".webm", ".m4v", ".avi"):
                                ctype = response.headers.get("Content-Type", "").lower()
                                ext = ".mov" if "quicktime" in ctype else ".webm" if "webm" in ctype else ".mp4"
                            from logic import safe_filename
                            fname = f"{i:02d}_{safe_filename(angle['name'])}{ext}"
                            if fname in used_names:
                                fname = f"{i:02d}_{safe_filename(angle['name'])}_{len(used_names)}{ext}"
                            used_names.add(fname)
                            with archive.open(fname, mode="w", force_zip64=True) as out:
                                for chunk in response.iter_content(chunk_size=1024 * 1024):
                                    if not chunk:
                                        continue
                                    total += len(chunk)
                                    if total > max_total_bytes:
                                        raise HTTPException(413, "Videos exceed configured ZIP size limit")
                                    out.write(chunk)
                        success += 1
                    except HTTPException:
                        raise
                    except (requests.RequestException, ValueError, OSError) as exc:
                        failures.append(f"{i}. {angle['name']}: {exc}")
                if failures:
                    archive.writestr("Missing_Angles.txt", "Some source videos were unavailable:\n" + "\n".join(failures) + "\n")
            if success == 0:
                raise HTTPException(502, "No downloadable video angles were available")
            return path
        except Exception:
            cleanup_file(path)
            raise



# Browse authorized DV Sport FULL GAME clips without grading them.
@app.get("/api/v1/dvsport/matches", dependencies=[Depends(require_api_key)])
def browse_dvsport_matches(date_from: date, date_to: date,
                           conference: str = Query("", max_length=80),
                           q: str = Query("", max_length=100)):
    return search_matches(setting("DVSPORT_COOKIE"), date_from, date_to, conference, q)


@app.get("/api/v1/dvsport/matches/{match_id}/plays", dependencies=[Depends(require_api_key)])
def browse_dvsport_plays(match_id: str):
    return plays_in_match(setting("DVSPORT_COOKIE"), match_id)


@app.post("/api/v1/dvsport/matches/{match_id}/plays/{play_number}/import", dependencies=[Depends(require_api_key)])
def import_dvsport_play(match_id: str, play_number: int):
    return import_play(client(), setting("DVSPORT_COOKIE"), match_id, play_number)


@app.get("/api/v1/plays/{play_id}/angles/{angle_index}/watch")
def watch_angle(play_id: str, angle_index: int,
                expires: int = Query(..., ge=1),
                sig: str = Query(..., min_length=64, max_length=64)):
    if not valid_download_token(play_id, expires, sig, signing_secret()):
        raise HTTPException(403, "Expired or invalid video link. Refresh the Google Sheet.")
    angles = get_angles(get_play(play_id))
    if not (0 <= angle_index < len(angles)):
        raise HTTPException(404, "Video angle not found")
    try:
        signed_url = refresh_media_url(angles[angle_index]["url"])
        approved_video_host(signed_url)
    except (requests.RequestException, ValueError, OSError) as exc:
        raise HTTPException(502, "Could not retrieve the video from DV Sport") from exc
    return RedirectResponse(signed_url, status_code=302)


@app.get("/api/v1/plays/{play_id}/download")
def download_play(play_id: str, background_tasks: BackgroundTasks,
                  expires: int = Query(..., ge=1), sig: str = Query(..., min_length=64, max_length=64)):
    if not valid_download_token(play_id, expires, sig, signing_secret()):
        raise HTTPException(403, "Expired or invalid download link. Refresh the Google Sheet.")
    play = get_play(play_id)
    angles = get_angles(play, refresh=True)
    if not angles:
        raise HTTPException(404, "This play has no downloadable angles")
    comments = get_comments_for_play(play_id)
    file_path = make_zip(play, angles, comments)
    background_tasks.add_task(cleanup_file, file_path)
    return FileResponse(file_path, media_type="application/zip",
                        filename=zip_name(play), background=background_tasks)
