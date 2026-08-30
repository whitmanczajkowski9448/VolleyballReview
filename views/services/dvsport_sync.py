import hashlib
import re
import time
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie

import requests
from requests.cookies import RequestsCookieJar


# ============================================================
# SETTINGS
# ============================================================

BASE_URL = "https://filmroom.dvsport360.com"

LIBRARY_URL = (
    f"{BASE_URL}/FilmRoomContent/GetUsersRegionContent"
)

PLAYLIST_URL = (
    f"{BASE_URL}/VideoPlayer/GetPlaylistData"
)

ORG_ID = 22339
YEAR = "2026"

SEASON_START_DATE = date(2026, 1, 1)
SEASON_END_DATE = date(2026, 12, 31)

# Default UI range: season start through today, capped to the 2026 season.
DEFAULT_END_DATE = min(date.today(), SEASON_END_DATE)
DEFAULT_START_DATE = max(
    SEASON_START_DATE,
    DEFAULT_END_DATE - timedelta(days=7),
)

TARGET_CONFERENCES = {
    "BIG TEN": "BIG TEN",
    "MVC": "MVC",
    "MAC": "MAC",
}

MAX_LIBRARY_PAGES = 500
REQUEST_DELAY_SECONDS = 0.10


# ============================================================
# PROGRESS CALLBACK
# ============================================================

def emit_progress(
    callback,
    fraction,
    stage,
    message,
    **extra,
):
    if callback is None:
        return

    fraction = max(
        0.0,
        min(
            1.0,
            float(fraction),
        ),
    )

    event = {
        "fraction": fraction,
        "stage": stage,
        "message": message,
    }

    event.update(extra)

    callback(event)


# ============================================================
# BASIC HELPERS
# ============================================================

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


def normalize_field_name(name):
    return clean_text(name)


# ============================================================
# AUTH / REQUESTS
# ============================================================

def standard_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "application/json, "
            "text/javascript, "
            "*/*; q=0.01"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": (
            "application/x-www-form-urlencoded; "
            "charset=UTF-8"
        ),
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
        "X-Requested-With": "XMLHttpRequest",
    }


def cookiejar_from_header(cookie_header):
    jar = RequestsCookieJar()

    parsed = SimpleCookie()
    parsed.load(cookie_header)

    if not parsed:
        raise RuntimeError(
            "DVSPORT_COOKIE could not be parsed. "
            "Store only the Cookie request-header value "
            "in secrets.toml."
        )

    for key, morsel in parsed.items():
        jar.set(
            key,
            morsel.value,
            domain="filmroom.dvsport360.com",
            path="/",
        )

    return jar


def make_session(cookie_header):
    session = requests.Session()

    session.headers.update(
        standard_headers()
    )

    session.cookies.update(
        cookiejar_from_header(
            cookie_header
        )
    )

    return session


def response_to_json(
    response,
    description,
):
    if response.status_code in (
        301,
        302,
        303,
        307,
        308,
    ):
        raise RuntimeError(
            f"{description}: DV Sport redirected the request. "
            "Your DVSPORT_COOKIE is probably expired."
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"{description}: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{description}: expected JSON. "
            "Your DVSPORT_COOKIE may be expired."
        ) from exc

    return data


def get_library_page(
    session,
    page_number,
):
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

    return response_to_json(
        response,
        f"Library page {page_number}",
    )


def get_playlist_data(
    session,
    dvplaylist_url,
):
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

    return response_to_json(
        response,
        "GetPlaylistData",
    )


def verify_dvsport_session(
    cookie_header,
):
    session = make_session(
        cookie_header
    )

    first_page = get_library_page(
        session,
        1,
    )

    return session, first_page


# ============================================================
# LIBRARY DISCOVERY
# ============================================================

def item_key(item):
    return (
        clean_text(item.get("Id")),
        clean_text(item.get("Url")),
        clean_text(item.get("InternalId")),
    )


def discover_library(
    session,
    first_page_data,
    progress_callback=None,
):
    all_items = {}
    seen_page_hashes = set()

    for page_number in range(
        1,
        MAX_LIBRARY_PAGES + 1,
    ):
        emit_progress(
            progress_callback,
            0.05,
            "Discovering DV Sport library",
            f"Reading library page {page_number:,}...",
            library_page=page_number,
        )

        if page_number == 1:
            data = first_page_data
        else:
            data = get_library_page(
                session,
                page_number,
            )

        content = (
            data.get("Content")
            or []
        )

        if not content:
            break

        page_signature = "\n".join(
            (
                f"{item.get('Id', '')}|"
                f"{item.get('Url', '')}|"
                f"{item.get('InternalId', '')}"
            )
            for item in content
        )

        page_hash = hashlib.sha256(
            page_signature.encode(
                "utf-8",
                errors="ignore",
            )
        ).hexdigest()

        if page_hash in seen_page_hashes:
            break

        seen_page_hashes.add(page_hash)

        before = len(all_items)

        for item in content:
            all_items[
                item_key(item)
            ] = item

        added = len(all_items) - before

        if (
            page_number > 1
            and added == 0
        ):
            break

        time.sleep(0.03)

    return list(
        all_items.values()
    )


# ============================================================
# PATH / TITLE PARSING
# ============================================================

def conference_from_id(item_id):
    parts = clean_text(
        item_id
    ).split("/")

    if len(parts) < 4:
        return None

    if (
        parts[0].upper() != "HOME"
        or parts[1].upper() != "VIDEOS"
        or parts[2] != YEAR
    ):
        return None

    return TARGET_CONFERENCES.get(
        parts[3].strip().upper()
    )


def parse_leading_date(title):
    match = re.match(
        r"^(?P<date>\d{2}[.\-]\d{2}[.\-]\d{2})\s*-\s*",
        clean_text(title),
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    raw = (
        match.group("date")
        .replace("-", ".")
    )

    try:
        return datetime.strptime(
            raw,
            "%m.%d.%y",
        ).date()
    except ValueError:
        return None


def in_date_range(
    title,
    start_date,
    end_date,
):
    parsed = parse_leading_date(
        title
    )

    return (
        parsed is not None
        and start_date <= parsed <= end_date
    )


def parse_challenge_playlist_title(title):
    result = {
        "date": parse_leading_date(title),
        "match": clean_text(title),
    }

    text = clean_text(title)

    match = re.match(
        (
            r"^\d{2}[.\-]\d{2}[.\-]\d{2}\s*-\s*"
            r"(?P<match>.+?)"
            r"\s*-\s*REVIEWS"
            r"(?:\s*-\s*\d{2}-\d{2}-\d{2})?$"
        ),
        text,
        flags=re.IGNORECASE,
    )

    if match:
        result["match"] = (
            match.group("match")
            .strip()
        )

    return result


def parse_poi_playlist_title(title):
    """
    Handles titles such as:

    08.27.26 - SMU VS PENN ST - POIS - 20-22-49
    08.27.26 - SMU VS PENN ST - POI - PLAY 015 - 20-22-49
    """
    result = {
        "date": parse_leading_date(title),
        "match": clean_text(title),
    }

    text = clean_text(title)

    match = re.match(
        (
            r"^\d{2}[.\-]\d{2}[.\-]\d{2}\s*-\s*"
            r"(?P<match>.+?)"
            r"\s*-\s*POIS?"
            r"(?:\s*-\s*PLAY\s+\d+)?"
            r"(?:\s*-\s*\d{2}-\d{2}-\d{2})?$"
        ),
        text,
        flags=re.IGNORECASE,
    )

    if match:
        result["match"] = (
            match.group("match")
            .strip()
        )

    return result


def poi_match_key(item):
    parsed = parse_poi_playlist_title(
        item.get("Title")
    )

    match_date = parsed["date"]

    return (
        item.get("_Conference", ""),
        (
            match_date.isoformat()
            if match_date
            else ""
        ),
        parsed["match"].upper(),
    )


# ============================================================
# CHALLENGE PLAYLIST DISCOVERY
# ============================================================

def find_challenge_playlists(
    items,
    start_date,
    end_date,
):
    results = []
    seen_urls = set()

    for item in items:
        item_id = clean_text(
            item.get("Id")
        )

        url = clean_text(
            item.get("Url")
        )

        title = clean_text(
            item.get("Title")
        )

        conference = conference_from_id(
            item_id
        )

        if conference is None:
            continue

        upper_id = item_id.upper()

        if (
            f"/VIDEOS/{YEAR}/"
            not in upper_id
        ):
            continue

        if (
            "/REVIEWS/REVIEWS BY GAME/"
            not in upper_id
        ):
            continue

        if item.get("Type") != 0:
            continue

        if not url.upper().endswith(
            ".DVPLAYLIST"
        ):
            continue

        if not in_date_range(
            title,
            start_date,
            end_date,
        ):
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        copy = dict(item)
        copy["_Conference"] = conference
        copy["_SourceType"] = "Challenge"

        results.append(copy)

    results.sort(
        key=lambda item: (
            parse_leading_date(
                item.get("Title")
            )
            or start_date,
            item.get("_Conference", ""),
            clean_text(
                item.get("Title")
            ),
        )
    )

    return results


# ============================================================
# POI PLAYLIST DISCOVERY
# ============================================================

def find_poi_playlist_groups(
    items,
    start_date,
    end_date,
):
    """
    Return POI playlist groups by conference/date/match.

    Each group contains:
      combined:  - POIS - playlist(s)
      individual: - POI - PLAY ### - playlist(s)

    We prefer combined playlists at import time because they contain
    all POIs for the match and avoid duplicate importing.
    """
    groups = {}

    for item in items:
        item_id = clean_text(
            item.get("Id")
        )

        url = clean_text(
            item.get("Url")
        )

        title = clean_text(
            item.get("Title")
        )

        conference = conference_from_id(
            item_id
        )

        if conference is None:
            continue

        upper_id = item_id.upper()
        upper_title = title.upper()

        expected_prefix = (
            f"HOME/VIDEOS/{YEAR}/"
            f"{conference}/POI/"
        )

        if not upper_id.startswith(
            expected_prefix.upper()
        ):
            continue

        if item.get("Type") != 0:
            continue

        if not url.upper().endswith(
            ".DVPLAYLIST"
        ):
            continue

        if not in_date_range(
            title,
            start_date,
            end_date,
        ):
            continue

        # Only the two real POI playlist forms.
        is_individual = bool(
            re.search(
                r"\s-\sPOI\s-\sPLAY\s+\d+",
                upper_title,
            )
        )

        is_combined = bool(
            re.search(
                r"\s-\sPOIS(?:\s-|$)",
                upper_title,
            )
        )

        if not (
            is_individual
            or is_combined
        ):
            continue

        copy = dict(item)
        copy["_Conference"] = conference
        copy["_SourceType"] = "POI"

        key = poi_match_key(copy)

        if key not in groups:
            groups[key] = {
                "combined": [],
                "individual": [],
            }

        if is_combined:
            groups[key]["combined"].append(
                copy
            )
        else:
            groups[key]["individual"].append(
                copy
            )

    # Best combined snapshot first:
    # most plays, then most recently modified.
    for group in groups.values():
        group["combined"].sort(
            key=lambda item: (
                to_int(
                    item.get("NumberOfPlays")
                )
                or -1,
                to_int(
                    item.get("LastModifiedTicks")
                )
                or 0,
            ),
            reverse=True,
        )

        group["individual"].sort(
            key=lambda item: clean_text(
                item.get("Title")
            )
        )

    return groups


# ============================================================
# DV SPORT PLAY FIELDS
# ============================================================

def fields_for_play(
    playlist,
    play,
):
    fields = {}

    headings = (
        playlist.get("Headings")
        or playlist.get("headings")
        or []
    )

    values = (
        play.get("Data")
        or play.get("data")
        or []
    )

    # Headings can be strings or heading dictionaries.
    normalized_headings = []

    for heading in headings:
        if isinstance(heading, dict):
            heading_name = (
                heading.get("internalName")
                or heading.get("internalname")
                or heading.get("Value")
                or heading.get("value")
                or ""
            )
        else:
            heading_name = heading

        normalized_headings.append(
            normalize_field_name(
                heading_name
            )
        )

    for heading, value in zip(
        normalized_headings,
        values,
    ):
        fields[heading] = value

    for field in (
        play.get("DataVerbose")
        or play.get("dataVerbose")
        or []
    ):
        name = normalize_field_name(
            field.get("internalName")
            or field.get("internalname")
        )

        if not name:
            continue

        value = (
            field.get("fieldData")
            if "fieldData" in field
            else field.get("fielddata")
        )

        if (
            name not in fields
            or fields[name] in (
                None,
                "",
            )
        ):
            fields[name] = value

    # Some source headings contain a trailing space.
    # Make trimmed aliases as well.
    for key in list(fields.keys()):
        stripped = clean_text(key)

        if (
            stripped
            and stripped not in fields
        ):
            fields[stripped] = fields[key]

    return fields


# ============================================================
# VIDEO EXTRACTION
# ============================================================

def normalize_angle_label(label):
    text = clean_text(label)

    if not text:
        return "Video"

    upper = text.upper()

    if upper in {
        "PGM",
        "PROGRAM",
        "PROGRAM FEED",
        "PROGRAM OUTPUT",
    }:
        return "PGM"

    if upper in {
        "RO",
        "REPLAY",
        "REPLAY OUTPUT",
        "REPLAY-OUTPUT",
        "REPLAY OUT",
    }:
        return "REPLAY OUTPUT"

    return text


def angle_priority(label):
    normalized = (
        normalize_angle_label(
            label
        )
        .upper()
    )

    if normalized == "PGM":
        return 0

    if normalized == "REPLAY OUTPUT":
        return 1

    return 10


def map_lookup(mapping, key):
    """
    DV Sport media maps have appeared as either dictionaries
    or lists of objects. Support both.
    """
    if not mapping:
        return ""

    if isinstance(mapping, dict):
        return clean_text(
            mapping.get(key)
        )

    if isinstance(mapping, list):
        for item in mapping:
            if not isinstance(item, dict):
                continue

            possible_key = clean_text(
                item.get("name")
                or item.get("Name")
                or item.get("key")
                or item.get("Key")
                or item.get("filename")
                or item.get("FileName")
                or item.get("clipName")
            )

            if possible_key != key:
                continue

            return clean_text(
                item.get("url")
                or item.get("Url")
                or item.get("sasUrl")
                or item.get("SasUrl")
                or item.get("mediaUrl")
                or item.get("MediaUrl")
            )

    return ""


def extract_video_angles(
    root_data,
    playlist,
    play,
):
    """
    Videos are always specific to THIS play.
    There are no universal camera placeholders.
    """
    sas_map = (
        root_data.get("SasMap")
        or root_data.get("sasMap")
        or {}
    )

    media_map = (
        playlist.get("MediaMap")
        or playlist.get("mediamap")
        or {}
    )

    by_url = {}

    clips = (
        play.get("Clips")
        or play.get("clips")
        or []
    )

    for clip in clips:
        clip_name = clean_text(
            clip.get("Name")
            or clip.get("name")
        )

        raw_label = clean_text(
            clip.get("Label")
            or clip.get("label")
        )

        if not clip_name:
            continue

        url = (
            map_lookup(
                sas_map,
                clip_name,
            )
            or map_lookup(
                media_map,
                clip_name,
            )
        )

        if not url:
            continue

        label = normalize_angle_label(
            raw_label
        )

        candidate = {
            "angle_name": label,
            "video_url": url,
        }

        current = by_url.get(url)

        if (
            current is None
            or angle_priority(label)
            < angle_priority(
                current["angle_name"]
            )
        ):
            by_url[url] = candidate

    angles = list(
        by_url.values()
    )

    angles.sort(
        key=lambda angle: (
            angle_priority(
                angle["angle_name"]
            ),
            angle["angle_name"].upper(),
        )
    )

    return angles


# ============================================================
# STABLE IDS
# ============================================================

def build_challenge_dvsport_id(
    fields,
    play,
    library_item,
):
    # Preserve the same ID logic already used for challenges,
    # so existing challenge records update rather than duplicate.
    review_id = clean_text(
        fields.get("ID")
    )

    if review_id:
        return f"review:{review_id}"

    play_id = clean_text(
        play.get("PlayId")
    )

    if play_id:
        return f"play:{play_id}"

    internal_play_id = clean_text(
        play.get("InternalPlayId")
    )

    if internal_play_id:
        return f"internal:{internal_play_id}"

    raw = "|".join(
        [
            clean_text(
                library_item.get(
                    "InternalId"
                )
            ),
            clean_text(
                library_item.get(
                    "Title"
                )
            ),
            clean_text(
                play.get("PlayNumber")
            ),
            clean_text(
                fields.get("SET")
            ),
            clean_text(
                fields.get("Home")
            ),
            clean_text(
                fields.get("Away")
            ),
            clean_text(
                fields.get(
                    "REVIEW INITIATOR"
                )
            ),
            clean_text(
                fields.get(
                    "REVIEW TYPE"
                )
            ),
        ]
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]

    return f"fallback:{digest}"


def build_poi_dvsport_id(
    fields,
    play,
    library_item,
):
    """
    Prefix POI identifiers so a POI cannot accidentally overwrite
    a challenge record that happens to reference the same PlayId.
    """

    play_id = clean_text(
        play.get("PlayId")
    )

    if play_id:
        return f"poi:play:{play_id}"

    internal_play_id = clean_text(
        play.get("InternalPlayId")
    )

    if internal_play_id:
        return (
            f"poi:internal:"
            f"{internal_play_id}"
        )

    play_number = (
        clean_text(
            fields.get("PLAY_#")
        )
        or clean_text(
            play.get("PlayNumber")
        )
    )

    parsed = parse_poi_playlist_title(
        library_item.get("Title")
    )

    raw = "|".join(
        [
            clean_text(
                library_item.get(
                    "_Conference"
                )
            ),
            (
                parsed["date"].isoformat()
                if parsed["date"]
                else ""
            ),
            parsed["match"],
            play_number,
            clean_text(
                fields.get("SET")
            ),
            clean_text(
                fields.get("Home")
            ),
            clean_text(
                fields.get("Away")
            ),
        ]
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]

    return f"poi:fallback:{digest}"


# ============================================================
# EXTRACT CHALLENGES
# ============================================================

def challenger_from_initiator(
    initiator,
):
    text = clean_text(initiator)

    match = re.search(
        r"CHALLENGED\s*:\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )

    return (
        match.group(1).strip()
        if match
        else text
    )


def extract_challenges_from_playlist(
    root_data,
    library_item,
):
    playlist = (
        root_data.get("Playlist")
        or root_data.get("playlist")
        or {}
    )

    title_info = (
        parse_challenge_playlist_title(
            library_item.get("Title")
        )
    )

    conference = (
        library_item.get(
            "_Conference",
            "",
        )
    )

    records = []

    plays = (
        playlist.get("Plays")
        or playlist.get("plays")
        or []
    )

    for play in plays:
        fields = fields_for_play(
            playlist,
            play,
        )

        initiator = clean_text(
            fields.get(
                "REVIEW INITIATOR"
            )
        )

        review_type = clean_text(
            fields.get(
                "REVIEW TYPE"
            )
        )

        review_result = clean_text(
            fields.get(
                "REVIEW RESULT"
            )
            or fields.get(
                "REVIEW RESULT "
            )
        )

        initiator_upper = initiator.upper()
        review_type_upper = (
            review_type.upper()
        )

        if (
            not initiator
            or "CHALLENG"
            not in initiator_upper
        ):
            continue

        if (
            "POI" in initiator_upper
            or "POINT OF INTEREST"
            in initiator_upper
            or "POI" in review_type_upper
            or "POINT OF INTEREST"
            in review_type_upper
        ):
            continue

        home_score = clean_text(
            fields.get("Home")
        )

        away_score = clean_text(
            fields.get("Away")
        )

        score = (
            f"{home_score}-{away_score}"
            if (
                home_score
                or away_score
            )
            else ""
        )

        record = {
            "dvsport_id":
                build_challenge_dvsport_id(
                    fields,
                    play,
                    library_item,
                ),

            "conference":
                conference,

            "match_date":
                (
                    title_info["date"]
                    .isoformat()
                    if title_info["date"]
                    else None
                ),

            "match_name":
                title_info["match"],

            "play_type":
                "Challenge",

            "set_number":
                to_int(
                    fields.get("SET")
                ),

            "score":
                score,

            "challenging_team":
                challenger_from_initiator(
                    initiator
                )
                or None,

            "challenge_type":
                review_type
                or None,

            "challenge_result":
                review_result
                or None,

            "challenge_length_seconds":
                to_int(
                    fields.get(
                        "REVIEW TIME"
                    )
                ),
        }

        angles = extract_video_angles(
            root_data,
            playlist,
            play,
        )

        records.append(
            (
                record,
                angles,
            )
        )

    return records


# ============================================================
# EXTRACT POIs
# ============================================================

def extract_pois_from_playlist(
    root_data,
    library_item,
):
    """
    Every play in a playlist discovered from the conference /POI/
    folder is a POI.

    This intentionally does NOT depend on REVIEW INITIATOR, because
    POI playlists use their own metadata schema.
    """
    playlist = (
        root_data.get("Playlist")
        or root_data.get("playlist")
        or {}
    )

    title_info = (
        parse_poi_playlist_title(
            library_item.get("Title")
        )
    )

    conference = (
        library_item.get(
            "_Conference",
            "",
        )
    )

    records = []

    plays = (
        playlist.get("Plays")
        or playlist.get("plays")
        or []
    )

    for play in plays:
        fields = fields_for_play(
            playlist,
            play,
        )

        home_score = clean_text(
            fields.get("Home")
        )

        away_score = clean_text(
            fields.get("Away")
        )

        score = (
            f"{home_score}-{away_score}"
            if (
                home_score
                or away_score
            )
            else ""
        )

        record = {
            "dvsport_id":
                build_poi_dvsport_id(
                    fields,
                    play,
                    library_item,
                ),

            "conference":
                conference,

            "match_date":
                (
                    title_info["date"]
                    .isoformat()
                    if title_info["date"]
                    else None
                ),

            "match_name":
                title_info["match"],

            "play_type":
                "POI",

            "set_number":
                to_int(
                    fields.get("SET")
                ),

            "score":
                score,

            # Challenge-only columns intentionally remain blank.
            "challenging_team":
                None,

            "challenge_type":
                None,

            "challenge_result":
                None,

            "challenge_length_seconds":
                None,
        }

        angles = extract_video_angles(
            root_data,
            playlist,
            play,
        )

        records.append(
            (
                record,
                angles,
            )
        )

    return records


# ============================================================
# DATABASE
# ============================================================

def get_existing_play(
    supabase,
    dvsport_id,
):
    response = (
        supabase
        .table("plays")
        .select(
            "id,dvsport_id"
        )
        .eq(
            "dvsport_id",
            dvsport_id,
        )
        .limit(1)
        .execute()
    )

    return (
        response.data[0]
        if response.data
        else None
    )


def upsert_play(
    supabase,
    record,
):
    """
    Only DV Sport-owned fields are sent here.
    Manual review/tagging fields are preserved.
    """
    existing = get_existing_play(
        supabase,
        record["dvsport_id"],
    )

    if existing:
        (
            supabase
            .table("plays")
            .update(record)
            .eq(
                "id",
                existing["id"],
            )
            .execute()
        )

        return (
            existing["id"],
            "updated",
        )

    response = (
        supabase
        .table("plays")
        .insert(record)
        .execute()
    )

    if response.data:
        return (
            response.data[0]["id"],
            "inserted",
        )

    inserted = get_existing_play(
        supabase,
        record["dvsport_id"],
    )

    if not inserted:
        raise RuntimeError(
            "Inserted play could not be read back from Supabase."
        )

    return (
        inserted["id"],
        "inserted",
    )


def sync_video_angles(
    supabase,
    play_id,
    angles,
):
    """
    Video rows are specific to one play.

    Identity:
        play_id + video_url

    This matches the database unique constraint.
    """
    existing_response = (
        supabase
        .table("video_angles")
        .select(
            "id,angle_name,video_url"
        )
        .eq(
            "play_id",
            play_id,
        )
        .execute()
    )

    existing = (
        existing_response.data
        or []
    )

    existing_by_url = {
        clean_text(
            row.get("video_url")
        ): row
        for row in existing
        if clean_text(
            row.get("video_url")
        )
    }

    incoming_by_url = {
        angle["video_url"]: angle
        for angle in angles
        if clean_text(
            angle.get("video_url")
        )
    }

    inserted = 0
    updated = 0
    deleted = 0

    for url, angle in (
        incoming_by_url.items()
    ):
        name = angle["angle_name"]
        current = existing_by_url.get(
            url
        )

        if current:
            if clean_text(
                current.get("angle_name")
            ) != name:
                (
                    supabase
                    .table("video_angles")
                    .update(
                        {
                            "angle_name":
                                name
                        }
                    )
                    .eq(
                        "id",
                        current["id"],
                    )
                    .execute()
                )

                updated += 1

        else:
            (
                supabase
                .table("video_angles")
                .insert(
                    {
                        "play_id":
                            play_id,
                        "angle_name":
                            name,
                        "video_url":
                            url,
                    }
                )
                .execute()
            )

            inserted += 1

    for url, current in (
        existing_by_url.items()
    ):
        if url not in incoming_by_url:
            (
                supabase
                .table("video_angles")
                .delete()
                .eq(
                    "id",
                    current["id"],
                )
                .execute()
            )

            deleted += 1

    return (
        inserted,
        updated,
        deleted,
    )


def import_records(
    supabase,
    records,
):
    result = {
        "inserted": 0,
        "updated": 0,
        "angles_inserted": 0,
        "angles_updated": 0,
        "angles_deleted": 0,
    }

    for record, angles in records:
        play_id, action = upsert_play(
            supabase,
            record,
        )

        result[action] += 1

        (
            angle_inserted,
            angle_updated,
            angle_deleted,
        ) = sync_video_angles(
            supabase,
            play_id,
            angles,
        )

        result["angles_inserted"] += (
            angle_inserted
        )

        result["angles_updated"] += (
            angle_updated
        )

        result["angles_deleted"] += (
            angle_deleted
        )

    return result


# ============================================================
# POI GROUP IMPORT
# ============================================================

def load_poi_group_records(
    session,
    group,
):
    """
    Try combined POIS snapshots first.

    If a combined playlist successfully returns at least one play,
    use it and DO NOT import the individual playlists for that match.

    If no combined playlist is usable, fall back to every individual
    POI playlist.
    """

    combined_errors = []

    for combined_item in (
        group["combined"]
    ):
        try:
            root_data = get_playlist_data(
                session,
                combined_item["Url"],
            )

            records = (
                extract_pois_from_playlist(
                    root_data,
                    combined_item,
                )
            )

            if records:
                return (
                    records,
                    "combined",
                    combined_item,
                    combined_errors,
                )

        except Exception as exc:
            combined_errors.append(
                {
                    "title":
                        clean_text(
                            combined_item.get(
                                "Title"
                            )
                        ),
                    "error":
                        str(exc),
                }
            )

    # No working combined POIS playlist.
    # Fall back to every individual POI playlist.
    all_records = []
    individual_errors = []

    for item in (
        group["individual"]
    ):
        try:
            root_data = get_playlist_data(
                session,
                item["Url"],
            )

            records = (
                extract_pois_from_playlist(
                    root_data,
                    item,
                )
            )

            all_records.extend(records)

        except Exception as exc:
            individual_errors.append(
                {
                    "title":
                        clean_text(
                            item.get(
                                "Title"
                            )
                        ),
                    "error":
                        str(exc),
                }
            )

    # Deduplicate within the match by POI dvsport_id.
    deduped = {}

    for record, angles in all_records:
        deduped[
            record["dvsport_id"]
        ] = (
            record,
            angles,
        )

    return (
        list(deduped.values()),
        "individual",
        None,
        (
            combined_errors
            + individual_errors
        ),
    )


# ============================================================
# MAIN SYNC
# ============================================================

def run_dvsport_sync(
    supabase,
    cookie_header,
    start_date=None,
    end_date=None,
    progress_callback=None,
):
    started = time.time()

    start_date = start_date or DEFAULT_START_DATE
    end_date = end_date or DEFAULT_END_DATE

    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise RuntimeError(
            "Start date and end date must be valid calendar dates."
        )

    if start_date > end_date:
        raise RuntimeError(
            "Start date cannot be after end date."
        )

    if (
        start_date < SEASON_START_DATE
        or end_date > SEASON_END_DATE
    ):
        raise RuntimeError(
            f"The current DV Sport sync is scoped to the {YEAR} season. "
            f"Choose dates from {SEASON_START_DATE:%m/%d/%Y} through "
            f"{SEASON_END_DATE:%m/%d/%Y}."
        )

    cookie_header = clean_text(
        cookie_header
    )

    if not cookie_header:
        raise RuntimeError(
            "DVSPORT_COOKIE is blank."
        )

    emit_progress(
        progress_callback,
        0.01,
        "Connecting to DV Sport",
        "Validating the saved DV Sport session cookie...",
    )

    session, first_page_data = (
        verify_dvsport_session(
            cookie_header
        )
    )

    emit_progress(
        progress_callback,
        0.04,
        "DV Sport connected",
        "Authentication succeeded. Reading the film library...",
    )

    library_items = discover_library(
        session,
        first_page_data,
        progress_callback,
    )

    challenge_playlists = (
        find_challenge_playlists(
            library_items,
            start_date,
            end_date,
        )
    )

    poi_groups = (
        find_poi_playlist_groups(
            library_items,
            start_date,
            end_date,
        )
    )

    total_work = (
        len(challenge_playlists)
        + len(poi_groups)
    )

    emit_progress(
        progress_callback,
        0.10,
        "Library scan complete",
        (
            f"{start_date:%m/%d/%Y} through {end_date:%m/%d/%Y}: "
            f"found {len(challenge_playlists):,} challenge "
            f"match playlist(s) and {len(poi_groups):,} "
            "match group(s) containing POIs."
        ),
        challenge_playlists=
            len(challenge_playlists),
        poi_match_groups=
            len(poi_groups),
    )

    summary = {
        "start_date":
            start_date.isoformat(),

        "end_date":
            end_date.isoformat(),

        "challenge_playlists":
            len(challenge_playlists),

        "poi_match_groups":
            len(poi_groups),

        "challenges_found":
            0,

        "pois_found":
            0,

        "plays_inserted":
            0,

        "plays_updated":
            0,

        "angles_inserted":
            0,

        "angles_updated":
            0,

        "angles_deleted":
            0,

        "poi_combined_groups":
            0,

        "poi_fallback_groups":
            0,

        "errors":
            [],

        "elapsed_seconds":
            0,
    }

    completed_work = 0

    # --------------------------------------------------------
    # CHALLENGES
    # --------------------------------------------------------

    for item in challenge_playlists:
        completed_work += 1

        title = clean_text(
            item.get("Title")
        )

        conference = item.get(
            "_Conference",
            "",
        )

        fraction = (
            0.10
            + 0.87
            * (
                (completed_work - 1)
                / max(total_work, 1)
            )
        )

        emit_progress(
            progress_callback,
            fraction,
            "Syncing challenges",
            f"{conference} • {title}",
            current_item=completed_work,
            total_items=total_work,
            challenges_found=
                summary["challenges_found"],
            pois_found=
                summary["pois_found"],
            plays_inserted=
                summary["plays_inserted"],
            plays_updated=
                summary["plays_updated"],
        )

        try:
            root_data = get_playlist_data(
                session,
                item["Url"],
            )

            records = (
                extract_challenges_from_playlist(
                    root_data,
                    item,
                )
            )

            summary[
                "challenges_found"
            ] += len(records)

            imported = import_records(
                supabase,
                records,
            )

            summary[
                "plays_inserted"
            ] += imported[
                "inserted"
            ]

            summary[
                "plays_updated"
            ] += imported[
                "updated"
            ]

            for key in (
                "angles_inserted",
                "angles_updated",
                "angles_deleted",
            ):
                summary[key] += imported[key]

        except Exception as exc:
            summary["errors"].append(
                {
                    "type": "Challenge",
                    "conference": conference,
                    "title": title,
                    "error": str(exc),
                }
            )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    # --------------------------------------------------------
    # POIs
    # --------------------------------------------------------

    sorted_poi_groups = sorted(
        poi_groups.items(),
        key=lambda pair: pair[0],
    )

    for key, group in sorted_poi_groups:
        completed_work += 1

        conference, match_date, match_name = (
            key
        )

        fraction = (
            0.10
            + 0.87
            * (
                (completed_work - 1)
                / max(total_work, 1)
            )
        )

        emit_progress(
            progress_callback,
            fraction,
            "Syncing plays of interest",
            (
                f"{conference} • "
                f"{match_date} • "
                f"{match_name}"
            ),
            current_item=completed_work,
            total_items=total_work,
            challenges_found=
                summary["challenges_found"],
            pois_found=
                summary["pois_found"],
            plays_inserted=
                summary["plays_inserted"],
            plays_updated=
                summary["plays_updated"],
        )

        try:
            (
                records,
                source_mode,
                selected_combined,
                poi_errors,
            ) = load_poi_group_records(
                session,
                group,
            )

            if source_mode == "combined":
                summary[
                    "poi_combined_groups"
                ] += 1
            else:
                summary[
                    "poi_fallback_groups"
                ] += 1

            summary[
                "pois_found"
            ] += len(records)

            imported = import_records(
                supabase,
                records,
            )

            summary[
                "plays_inserted"
            ] += imported[
                "inserted"
            ]

            summary[
                "plays_updated"
            ] += imported[
                "updated"
            ]

            for angle_key in (
                "angles_inserted",
                "angles_updated",
                "angles_deleted",
            ):
                summary[
                    angle_key
                ] += imported[
                    angle_key
                ]

            # Only surface fallback errors if the group ultimately
            # produced no POIs. A broken older combined snapshot is
            # harmless if another combined snapshot worked.
            if (
                not records
                and poi_errors
            ):
                for error in poi_errors:
                    summary["errors"].append(
                        {
                            "type": "POI",
                            "conference":
                                conference,
                            "title":
                                error["title"],
                            "error":
                                error["error"],
                        }
                    )

        except Exception as exc:
            summary["errors"].append(
                {
                    "type": "POI",
                    "conference": conference,
                    "title": (
                        f"{match_date} - "
                        f"{match_name}"
                    ),
                    "error": str(exc),
                }
            )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    summary["elapsed_seconds"] = (
        time.time() - started
    )

    emit_progress(
        progress_callback,
        1.0,
        "Sync complete",
        (
            f"{summary['challenges_found']:,} challenges and "
            f"{summary['pois_found']:,} POIs processed."
        ),
        **summary,
    )

    return summary
