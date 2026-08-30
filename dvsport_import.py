import os
import re
import time
import hashlib
from datetime import datetime, date
from http.cookies import SimpleCookie
from pathlib import Path
from getpass import getpass

import requests
from requests.cookies import RequestsCookieJar
from tqdm import tqdm
from supabase import create_client

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None

try:
    import tomllib
except ImportError:
    tomllib = None


# ============================================================
# SETTINGS
# ============================================================

BASE_URL = "https://filmroom.dvsport360.com"
LIBRARY_URL = f"{BASE_URL}/FilmRoomContent/GetUsersRegionContent"
PLAYLIST_URL = f"{BASE_URL}/VideoPlayer/GetPlaylistData"

ORG_ID = 22339
YEAR = "2026"
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 12, 31)

# Version 1 scope. Horizon can be added later.
TARGET_CONFERENCES = {
    "BIG TEN": "BIG TEN",
    "MVC": "MVC",
    "MAC": "MAC",
}

MAX_LIBRARY_PAGES = 500
REQUEST_DELAY_SECONDS = 0.10

PROJECT_DIR = Path(__file__).resolve().parent
SECRETS_FILE = PROJECT_DIR / ".streamlit" / "secrets.toml"


# ============================================================
# SUPABASE
# ============================================================

def load_supabase_client():
    if tomllib is None:
        raise RuntimeError(
            "Your Python version does not include tomllib. "
            "Use Python 3.11+ or install tomli."
        )

    if not SECRETS_FILE.exists():
        raise RuntimeError(
            f"Could not find {SECRETS_FILE}. "
            "Create .streamlit/secrets.toml first."
        )

    with open(SECRETS_FILE, "rb") as file:
        secrets = tomllib.load(file)

    url = str(secrets.get("SUPABASE_URL") or "").strip()
    key = str(secrets.get("SUPABASE_KEY") or "").strip()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_KEY is missing from "
            ".streamlit/secrets.toml."
        )

    return create_client(url, key)


# ============================================================
# HTTP / DV SPORT AUTHENTICATION
# ============================================================

def standard_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
        "X-Requested-With": "XMLHttpRequest",
    }


def cookiejar_from_header(cookie_header):
    jar = RequestsCookieJar()
    parsed = SimpleCookie()
    parsed.load(cookie_header)

    for key, morsel in parsed.items():
        jar.set(
            key,
            morsel.value,
            domain="filmroom.dvsport360.com",
            path="/",
        )

    return jar


def load_browser_cookies():
    jar = RequestsCookieJar()

    if browser_cookie3 is None:
        return jar

    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Edge", browser_cookie3.edge),
    ]

    domains = [
        "filmroom.dvsport360.com",
        "dvsport360.com",
    ]

    for browser_name, loader in browsers:
        for domain in domains:
            try:
                browser_jar = loader(domain_name=domain)
                for cookie in browser_jar:
                    jar.set_cookie(cookie)

                if len(jar):
                    print(
                        f"Loaded {len(jar)} DV Sport cookie(s) "
                        f"from {browser_name}."
                    )
                    return jar
            except Exception:
                pass

    return jar


def make_session(cookie_jar):
    session = requests.Session()
    session.headers.update(standard_headers())
    session.cookies.update(cookie_jar)
    return session


def response_to_json(response, description):
    if response.status_code in (301, 302, 303, 307, 308):
        raise RuntimeError(
            f"{description}: DV Sport redirected to "
            f"{response.headers.get('Location', 'another page')}. "
            "Your FilmRoom login session is probably expired."
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"{description}: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        text = response.text[:500].replace("\n", " ")
        raise RuntimeError(
            f"{description}: expected JSON. Your login may have expired.\n"
            f"First 500 characters: {text}"
        ) from exc

    if isinstance(data, dict) and data.get("Success") is False:
        raise RuntimeError(
            f"{description}: DV Sport returned Success=false: {data}"
        )

    return data


def get_library_page(session, page_number):
    payload = {
        "regionType": "Library",
        "canViewDocs": "true",
        "forceCacheRefresh": "false",
        "orgId": str(ORG_ID),
        "pageNumber": str(page_number),
    }

    response = session.post(
        LIBRARY_URL,
        data=payload,
        timeout=120,
        allow_redirects=False,
    )

    return response_to_json(response, f"Library page {page_number}")


def get_playlist_data(session, dvplaylist_url):
    payload = {
        "dvplaylistUrl": dvplaylist_url,
        "xro": "true",
    }

    response = session.post(
        PLAYLIST_URL,
        data=payload,
        timeout=180,
        allow_redirects=False,
    )

    return response_to_json(response, "GetPlaylistData")


def get_authenticated_session():
    # 1. Try local Chrome / Edge cookies.
    browser_jar = load_browser_cookies()

    if len(browser_jar):
        session = make_session(browser_jar)
        try:
            test = get_library_page(session, 1)
            if test.get("Success", True):
                print("FilmRoom session verified automatically.\n")
                return session, test
        except Exception as exc:
            print("Automatic browser-cookie login did not work:")
            print(exc)
            print()

    # 2. Optional environment variable.
    env_cookie = os.environ.get("DVSPORT_COOKIE", "").strip()
    if env_cookie:
        session = make_session(cookiejar_from_header(env_cookie))
        test = get_library_page(session, 1)
        print("FilmRoom session verified using DVSPORT_COOKIE.\n")
        return session, test

    # 3. Manual Cookie request-header paste.
    print("Could not automatically reuse your FilmRoom browser session.")
    print("In Chrome DevTools, copy ONLY the Cookie request-header value")
    print("from a successful FilmRoom request and paste it below.")
    print("The input is hidden and is not saved by this script.\n")

    cookie_header = getpass("Cookie header (hidden): ").strip()

    if not cookie_header:
        raise RuntimeError("No authenticated FilmRoom cookie was provided.")

    session = make_session(cookiejar_from_header(cookie_header))
    test = get_library_page(session, 1)
    print("FilmRoom session verified.\n")
    return session, test


# ============================================================
# LIBRARY DISCOVERY
# ============================================================

def item_key(item):
    return (
        str(item.get("Id") or ""),
        str(item.get("Url") or ""),
        str(item.get("InternalId") or ""),
    )


def discover_library(session, first_page_data):
    all_items = {}
    seen_page_hashes = set()

    for page_number in range(1, MAX_LIBRARY_PAGES + 1):
        if page_number == 1:
            data = first_page_data
        else:
            data = get_library_page(session, page_number)

        content = data.get("Content") or []

        if not content:
            print(f"Library page {page_number}: no content. Stopping.")
            break

        page_signature = "\n".join(
            f"{item.get('Id','')}|{item.get('Url','')}|{item.get('InternalId','')}"
            for item in content
        )
        page_hash = hashlib.sha256(
            page_signature.encode("utf-8", errors="ignore")
        ).hexdigest()

        if page_hash in seen_page_hashes:
            print(f"Library page {page_number}: repeated earlier page. Stopping.")
            break

        seen_page_hashes.add(page_hash)
        before = len(all_items)

        for item in content:
            all_items[item_key(item)] = item

        added = len(all_items) - before
        print(
            f"Library page {page_number}: "
            f"{len(content):,} items ({added:,} new)."
        )

        if page_number > 1 and added == 0:
            print("No new library items were added. Stopping.")
            break

        time.sleep(0.05)

    return list(all_items.values())


def conference_from_id(item_id):
    parts = item_id.split("/")

    if len(parts) < 4:
        return None

    if (
        parts[0].upper() != "HOME"
        or parts[1].upper() != "VIDEOS"
        or parts[2] != YEAR
    ):
        return None

    raw = parts[3].strip().upper()
    return TARGET_CONFERENCES.get(raw)


def parse_date_from_review_title(title):
    match = re.match(
        r"^(?P<date>\d{2}[.\-]\d{2}[.\-]\d{2})\s*-\s*",
        title.strip(),
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    raw = match.group("date").replace("-", ".")

    try:
        return datetime.strptime(raw, "%m.%d.%y").date()
    except ValueError:
        return None


def find_review_by_game_playlists(items):
    results = []
    seen_urls = set()

    for item in items:
        item_id = str(item.get("Id") or "")
        url = str(item.get("Url") or "")
        title = str(item.get("Title") or "")
        item_type = item.get("Type")

        conference = conference_from_id(item_id)
        if conference is None:
            continue

        normalized_id = item_id.upper()

        if f"/VIDEOS/{YEAR}/" not in normalized_id:
            continue
        if "/REVIEWS/REVIEWS BY GAME/" not in normalized_id:
            continue
        if "/POI/" in normalized_id:
            continue
        if item_type != 0:
            continue
        if not url.upper().endswith(".DVPLAYLIST"):
            continue

        match_date = parse_date_from_review_title(title)
        if match_date is None:
            continue
        if not (START_DATE <= match_date <= END_DATE):
            continue
        if url in seen_urls:
            continue

        seen_urls.add(url)
        copy = dict(item)
        copy["_Conference"] = conference
        copy["_MatchDate"] = match_date
        results.append(copy)

    results.sort(
        key=lambda x: (
            x["_MatchDate"],
            x["_Conference"],
            str(x.get("Title") or ""),
        )
    )
    return results


# ============================================================
# PLAY PARSING
# ============================================================

def normalize_field_name(name):
    return str(name or "").strip()


def fields_for_play(playlist, play):
    fields = {}

    headings = playlist.get("Headings") or []
    values = play.get("Data") or []

    for heading, value in zip(headings, values):
        fields[normalize_field_name(heading)] = value

    for field in play.get("DataVerbose") or []:
        name = normalize_field_name(field.get("internalName"))
        if not name:
            continue
        value = field.get("fieldData")
        if name not in fields or fields[name] in (None, ""):
            fields[name] = value

    return fields


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def to_int(value):
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def parse_playlist_title(title):
    result = {
        "date": None,
        "match": title,
    }

    pattern = re.compile(
        r"^(?P<date>\d{2}[.\-]\d{2}[.\-]\d{2})\s*-\s*"
        r"(?P<match>.+?)\s*-\s*REVIEWS\s*-\s*\d{2}-\d{2}-\d{2}$",
        re.IGNORECASE,
    )

    match = pattern.match(title.strip())
    if not match:
        return result

    raw_date = match.group("date").replace("-", ".")
    try:
        result["date"] = datetime.strptime(raw_date, "%m.%d.%y").date()
    except ValueError:
        result["date"] = None

    result["match"] = match.group("match").strip()
    return result


def challenger_from_initiator(initiator):
    text = clean_text(initiator)
    if not text:
        return ""

    match = re.search(
        r"CHALLENGED\s*:\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else text


def build_dvsport_id(fields, play, library_item):
    # Prefer the explicit DV Sport review ID when present.
    review_id = clean_text(fields.get("ID"))
    if review_id:
        return f"review:{review_id}"

    # Then use stable play identifiers when present.
    play_id = clean_text(play.get("PlayId"))
    if play_id:
        return f"play:{play_id}"

    internal_play_id = clean_text(play.get("InternalPlayId"))
    if internal_play_id:
        return f"internal:{internal_play_id}"

    # Last-resort deterministic identifier.
    raw = "|".join(
        [
            clean_text(library_item.get("InternalId")),
            clean_text(library_item.get("Title")),
            clean_text(play.get("PlayNumber")),
            clean_text(fields.get("SET")),
            clean_text(fields.get("Home")),
            clean_text(fields.get("Away")),
            clean_text(fields.get("REVIEW INITIATOR")),
            clean_text(fields.get("REVIEW TYPE")),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"fallback:{digest}"


def extract_video_angles(root_data, playlist, play):
    sas_map = root_data.get("SasMap") or {}
    media_map = playlist.get("MediaMap") or {}

    angles = []
    label_counts = {}

    for clip in play.get("Clips") or []:
        clip_name = clean_text(clip.get("Name"))
        label = clean_text(clip.get("Label")) or "Video"

        if not clip_name:
            continue

        url = clean_text(
            sas_map.get(clip_name)
            or media_map.get(clip_name)
            or ""
        )

        if not url:
            continue

        label_counts[label] = label_counts.get(label, 0) + 1
        number = label_counts[label]
        display_label = label if number == 1 else f"{label} {number}"

        angles.append(
            {
                "angle_name": display_label,
                "video_url": url,
            }
        )

    return angles


def extract_challenges_from_playlist(root_data, library_item):
    playlist = root_data.get("Playlist") or {}
    title = clean_text(library_item.get("Title"))
    title_info = parse_playlist_title(title)
    conference = library_item.get("_Conference", "")

    records = []

    for play in playlist.get("Plays") or []:
        fields = fields_for_play(playlist, play)

        initiator = clean_text(fields.get("REVIEW INITIATOR"))
        review_type = clean_text(fields.get("REVIEW TYPE"))
        review_result = clean_text(fields.get("REVIEW RESULT"))

        # Actual challenges only. POI and non-challenge review events are ignored.
        initiator_upper = initiator.upper()
        review_type_upper = review_type.upper()

        if not initiator or "CHALLENG" not in initiator_upper:
            continue

        if (
            "POI" in initiator_upper
            or "POINT OF INTEREST" in initiator_upper
            or "POI" in review_type_upper
            or "POINT OF INTEREST" in review_type_upper
        ):
            continue

        home_score = clean_text(fields.get("Home"))
        away_score = clean_text(fields.get("Away"))
        score = (
            f"{home_score}-{away_score}"
            if home_score or away_score
            else ""
        )

        # DV Sport stores REVIEW TIME as a numeric number of seconds.
        # Example: 84 means a challenge length of 1:24.
        review_time_seconds = to_int(fields.get("REVIEW TIME"))

        record = {
            "dvsport_id": build_dvsport_id(fields, play, library_item),
            "conference": conference,
            "match_date": (
                title_info["date"].isoformat()
                if title_info["date"]
                else None
            ),
            "match_name": title_info["match"],
            "play_type": "Challenge",
            "set_number": to_int(fields.get("SET")),
            "score": score,
            "challenging_team": challenger_from_initiator(initiator),
            "challenge_type": review_type or None,
            "challenge_result": review_result or None,
            "challenge_length_seconds": review_time_seconds,
        }

        angles = extract_video_angles(root_data, playlist, play)
        records.append((record, angles))

    return records


# ============================================================
# SUPABASE UPSERT
# ============================================================

def get_existing_play(supabase, dvsport_id):
    response = (
        supabase
        .table("plays")
        .select("id,dvsport_id")
        .eq("dvsport_id", dvsport_id)
        .limit(1)
        .execute()
    )

    return response.data[0] if response.data else None


def upsert_play(supabase, record):
    existing = get_existing_play(supabase, record["dvsport_id"])

    if existing:
        response = (
            supabase
            .table("plays")
            .update(record)
            .eq("id", existing["id"])
            .execute()
        )
        play_id = existing["id"]
        action = "updated"
    else:
        response = (
            supabase
            .table("plays")
            .insert(record)
            .execute()
        )

        if not response.data:
            # Read it back in case the API did not return representation.
            inserted = get_existing_play(supabase, record["dvsport_id"])
            if not inserted:
                raise RuntimeError(
                    f"Inserted play {record['dvsport_id']} but could not read it back."
                )
            play_id = inserted["id"]
        else:
            play_id = response.data[0]["id"]

        action = "inserted"

    return play_id, action


def sync_video_angles(supabase, play_id, angles):
    existing_response = (
        supabase
        .table("video_angles")
        .select("id,angle_name,video_url")
        .eq("play_id", play_id)
        .execute()
    )

    existing = existing_response.data or []
    existing_by_name = {
        clean_text(row.get("angle_name")): row
        for row in existing
        if clean_text(row.get("angle_name"))
    }

    inserted = 0
    updated = 0

    for angle in angles:
        name = angle["angle_name"]
        url = angle["video_url"]
        current = existing_by_name.get(name)

        if current:
            if clean_text(current.get("video_url")) != url:
                (
                    supabase
                    .table("video_angles")
                    .update({"video_url": url})
                    .eq("id", current["id"])
                    .execute()
                )
                updated += 1
        else:
            (
                supabase
                .table("video_angles")
                .insert(
                    {
                        "play_id": play_id,
                        "angle_name": name,
                        "video_url": url,
                    }
                )
                .execute()
            )
            inserted += 1

    return inserted, updated


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.time()

    print("=" * 68)
    print("DV SPORT -> SUPABASE CHALLENGE IMPORT")
    print("=" * 68)
    print(f"Season:       {YEAR}")
    print("Conferences:  BIG TEN, MVC, MAC")
    print("Play type:    CHALLENGES ONLY")
    print(f"Date range:   {START_DATE} through {END_DATE}")
    print()

    print("Connecting to Supabase...")
    supabase = load_supabase_client()
    print("Supabase connection ready.\n")

    print("Connecting to DV Sport...")
    session, first_page_data = get_authenticated_session()

    print("Discovering DV Sport library...")
    library_items = discover_library(session, first_page_data)
    print(f"\nUnique library items discovered: {len(library_items):,}\n")

    review_playlists = find_review_by_game_playlists(library_items)

    counts = {}
    for item in review_playlists:
        conference = item["_Conference"]
        counts[conference] = counts.get(conference, 0) + 1

    print("2026 review-by-game match playlists:")
    for conference in ["BIG TEN", "MVC", "MAC"]:
        print(f"  {conference:<10} {counts.get(conference, 0):>5}")
    print(f"  {'TOTAL':<10} {len(review_playlists):>5}\n")

    if not review_playlists:
        print("No matching review-by-game playlists were found.")
        return

    plays_inserted = 0
    plays_updated = 0
    angles_inserted = 0
    angles_updated = 0
    challenges_found = 0
    errors = []

    progress = tqdm(
        review_playlists,
        total=len(review_playlists),
        unit="match",
        desc="Importing",
        dynamic_ncols=True,
    )

    for item in progress:
        conference = item.get("_Conference", "")
        title = clean_text(item.get("Title"))
        progress.set_postfix_str(f"{conference}: {title[:38]}")

        try:
            root_data = get_playlist_data(session, item.get("Url"))
            records = extract_challenges_from_playlist(root_data, item)
            challenges_found += len(records)

            for record, angles in records:
                play_id, action = upsert_play(supabase, record)

                if action == "inserted":
                    plays_inserted += 1
                else:
                    plays_updated += 1

                new_angles, changed_angles = sync_video_angles(
                    supabase,
                    play_id,
                    angles,
                )
                angles_inserted += new_angles
                angles_updated += changed_angles

            time.sleep(REQUEST_DELAY_SECONDS)

        except Exception as exc:
            errors.append(
                {
                    "conference": conference,
                    "title": title,
                    "error": str(exc),
                }
            )

    elapsed = time.time() - started

    print("\n" + "=" * 68)
    print("IMPORT COMPLETE")
    print("=" * 68)
    print(f"Match playlists scanned:   {len(review_playlists):,}")
    print(f"Challenges found:          {challenges_found:,}")
    print(f"New plays inserted:        {plays_inserted:,}")
    print(f"Existing plays updated:    {plays_updated:,}")
    print(f"New video angles:          {angles_inserted:,}")
    print(f"Video angles refreshed:    {angles_updated:,}")
    print(f"Errors:                    {len(errors):,}")
    print(f"Elapsed time:              {elapsed:.1f} seconds")

    if errors:
        print("\nErrors:")
        for error in errors[:20]:
            print(
                f"- {error['conference']} | {error['title']}\n"
                f"  {error['error']}"
            )
        if len(errors) > 20:
            print(f"...and {len(errors) - 20} more error(s).")

    print("\nYour Streamlit app can now read the imported records from Supabase.")


if __name__ == "__main__":
    main()