import hashlib
import re
import time
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlsplit

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
# SYNC IDENTITY HELPERS
# ============================================================

def normalize_identity_text(value):
    """
    Normalize text only for record identity comparisons.

    This deliberately does not change the stored display value.
    """
    text = clean_text(value).upper()
    return re.sub(r"\s+", " ", text).strip()


def source_play_number(fields, play):
    """Return the DV Sport play number in a stable text form."""
    return (
        clean_text(fields.get("PLAY_#"))
        or clean_text(fields.get("PLAY #"))
        or clean_text(fields.get("PLAY NUMBER"))
        or clean_text(play.get("PlayNumber"))
        or clean_text(play.get("playNumber"))
    )


def canonical_match_play_id(
    prefix,
    conference,
    match_date,
    match_name,
    play_number,
):
    """
    Build an ID that survives DV Sport playlist republishing.

    POI and FAULT playlist snapshots can receive new playlist IDs and
    sometimes new source PlayId/InternalPlayId values.  Conference + match
    date + normalized match name + game play number is the stable identity.
    """
    if not play_number:
        return ""

    date_text = (
        match_date.isoformat()
        if isinstance(match_date, date)
        else clean_text(match_date)
    )

    raw = "|".join(
        [
            normalize_identity_text(prefix),
            normalize_identity_text(conference),
            date_text,
            normalize_identity_text(match_name),
            normalized_play_number(play_number),
        ]
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]

    return f"{prefix}:v2:{digest}"


def normalized_media_identity(value):
    """
    Normalize a DV Sport video URL for duplicate matching.

    Query strings/fragments are intentionally ignored because a media URL
    can acquire temporary parameters without becoming a different clip.
    """
    url = clean_text(value)

    if not url:
        return ""

    decoded = unquote(url)

    try:
        parsed = urlsplit(decoded)
        host = parsed.netloc.lower()
        path = re.sub(r"/+", "/", parsed.path).lower()
        return f"{host}{path}"
    except Exception:
        return decoded.split("?", 1)[0].split("#", 1)[0].lower()


def play_number_from_media_url(value):
    """Recover PLAY ### from a DV Sport clip URL when available."""
    text = unquote(clean_text(value))

    match = re.search(
        r"(?:^|[/\\])PLAY\s+0*(\d+)\b",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    try:
        return str(int(match.group(1)))
    except (TypeError, ValueError):
        return clean_text(match.group(1))


def normalized_play_number(value):
    text = clean_text(value)

    if not text:
        return ""

    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text.upper()


def public_database_record(record):
    """
    Remove transient sync-only keys before writing a play to Supabase.
    """
    return {
        key: value
        for key, value in record.items()
        if not str(key).startswith("_sync_")
    }


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


def _media_value_to_url(value):
    """Return a URL from the different DV Sport media-map shapes."""
    if isinstance(value, str):
        return clean_text(value)

    if isinstance(value, dict):
        return clean_text(
            value.get("url")
            or value.get("Url")
            or value.get("sasUrl")
            or value.get("SasUrl")
            or value.get("mediaUrl")
            or value.get("MediaUrl")
            or value.get("videoUrl")
            or value.get("VideoUrl")
            or value.get("src")
            or value.get("Src")
        )

    return ""


def _normalized_media_key(value):
    """Normalize a DV Sport clip/map key for tolerant matching."""
    text = unquote(clean_text(value)).replace("\\", "/")
    text = re.sub(r"/+", "/", text).strip().lower()
    return text


def map_lookup(mapping, key):
    """
    Resolve one clip name against DV Sport's media maps.

    DV Sport has returned these maps as dictionaries, lists of objects,
    and with small differences in case/URL encoding/path separators.
    The previous exact-key-only lookup could resolve PGM while silently
    missing the other camera files.
    """
    if not mapping:
        return ""

    wanted = _normalized_media_key(key)
    wanted_base = wanted.rsplit("/", 1)[-1]

    if isinstance(mapping, dict):
        # Fast exact lookup first.
        if key in mapping:
            url = _media_value_to_url(mapping.get(key))
            if url:
                return url

        # Then tolerate case, URL encoding, slash, and basename differences.
        for map_key, value in mapping.items():
            candidate = _normalized_media_key(map_key)
            candidate_base = candidate.rsplit("/", 1)[-1]
            if (
                candidate == wanted
                or candidate_base == wanted_base
            ):
                url = _media_value_to_url(value)
                if url:
                    return url

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
                or item.get("ClipName")
            )

            candidate = _normalized_media_key(possible_key)
            candidate_base = candidate.rsplit("/", 1)[-1]

            if not (
                candidate == wanted
                or candidate_base == wanted_base
            ):
                continue

            url = _media_value_to_url(item)
            if url:
                return url

    return ""


def _clip_direct_url(clip):
    """Use a URL embedded directly on a clip when DV Sport supplies one."""
    if not isinstance(clip, dict):
        return ""

    return clean_text(
        clip.get("VideoUrl")
        or clip.get("videoUrl")
        or clip.get("MediaUrl")
        or clip.get("mediaUrl")
        or clip.get("SasUrl")
        or clip.get("sasUrl")
        or clip.get("Url")
        or clip.get("url")
        or clip.get("Src")
        or clip.get("src")
    )


def _media_entry_items(mapping):
    """
    Yield (media_name, media_url) from any DV Sport media-map shape.

    DV Sport normally returns dictionaries, but older/alternate playlist
    payloads can contain lists of objects.  This keeps extraction shared by
    Challenges, POIs, and Faults.
    """
    if not mapping:
        return

    if isinstance(mapping, dict):
        for name, value in mapping.items():
            url = _media_value_to_url(value)
            if url:
                yield clean_text(name), url
        return

    if isinstance(mapping, list):
        for item in mapping:
            if not isinstance(item, dict):
                continue

            name = clean_text(
                item.get("name")
                or item.get("Name")
                or item.get("key")
                or item.get("Key")
                or item.get("filename")
                or item.get("FileName")
                or item.get("clipName")
                or item.get("ClipName")
                or item.get("Value")
            )
            url = _media_value_to_url(item)

            if name and url:
                yield name, url


def _play_number_from_media_name(value):
    """
    Return the numeric PLAY ### embedded in a DV Sport media filename/URL.
    """
    text = unquote(clean_text(value)).replace("\\", "/")

    match = re.search(
        r"(?:^|/)PLAY\s+0*(\d+)\s*-",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    try:
        return str(int(match.group(1)))
    except (TypeError, ValueError):
        return clean_text(match.group(1))


def _angle_name_from_media_name(value):
    """
    Infer the camera label from standard DV Sport media filenames.

    Examples:
      PLAY 104 - PGM...       -> PGM
      PLAY 104 - RO...        -> REPLAY OUTPUT
      PLAY 104 - ISO_CAM_7... -> CAM 7
    """
    name = unquote(clean_text(value)).replace("\\", "/").rsplit("/", 1)[-1]
    upper = name.upper()

    if re.search(r"\s-\s*PGM(?=\d|[._\s-]|$)", upper):
        return "PGM"

    if re.search(r"\s-\s*RO(?=\d|[._\s-]|$)", upper):
        return "REPLAY OUTPUT"

    cam_match = re.search(
        r"ISO[_\s-]*CAM[_\s-]*(\d+)",
        upper,
    )
    if cam_match:
        return f"CAM {int(cam_match.group(1))}"

    cam_match = re.search(
        r"(?:^|[\s_-])CAM(?:ERA)?[_\s-]*(\d+)",
        upper,
    )
    if cam_match:
        return f"CAM {int(cam_match.group(1))}"

    return normalize_angle_label(name)


def _prefer_media_url(current_url, candidate_url):
    """
    Prefer a signed/SAS URL when both maps describe the same media file.
    Otherwise retain the first valid URL.
    """
    current = clean_text(current_url)
    candidate = clean_text(candidate_url)

    if not current:
        return candidate
    if not candidate:
        return current

    current_has_query = "?" in current
    candidate_has_query = "?" in candidate

    if candidate_has_query and not current_has_query:
        return candidate

    return current


def _camera_number_from_label(value):
    match = re.search(
        r"\bCAM(?:ERA)?\s*(\d+)\b",
        clean_text(value),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _video_angle_sort_key(angle):
    name = clean_text(angle.get("angle_name"))
    upper = name.upper()

    if upper == "PGM":
        return (0, 0, "")

    if upper in {
        "REPLAY OUTPUT",
        "RO",
        "REPLAY",
    }:
        return (1, 0, "")

    camera_number = _camera_number_from_label(name)
    if camera_number is not None:
        return (2, camera_number, upper)

    return (
        3,
        0,
        upper,
    )


def extract_video_angles(
    root_data,
    playlist,
    play,
):
    """
    Extract EVERY available DV Sport angle belonging to one play.

    This deliberately uses TWO independent sources:

      1. play["Clips"] -- preserves DV Sport's explicit camera labels.
      2. SasMap / Playlist.MediaMap -- collects every media filename whose
         embedded PLAY ### matches this play.

    The second pass is critical.  Some DV Sport playlists expose media in
    the match-wide map even when a clip list is incomplete or represented
    differently.  Grouping by PLAY ### means the same logic works for
    Challenges, POIs, and Faults without mixing media between plays.

    At most 30 named URLs are returned because plays.video_urls is capped at
    30 entries in the database.
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

    clips = (
        play.get("Clips")
        or play.get("clips")
        or []
    )

    # PlayNumber is the authoritative grouping key.  Fall back to the
    # playlist fields because some older payloads omit PlayNumber.
    play_number = normalized_play_number(
        play.get("PlayNumber")
        or play.get("playNumber")
        or source_play_number(
            fields_for_play(
                playlist,
                play,
            ),
            play,
        )
    )

    # Label lookup from the explicit Clips array.
    clip_label_by_name = {}
    clip_order = []

    for clip_index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            continue

        clip_name = clean_text(
            clip.get("Name")
            or clip.get("name")
            or clip.get("FileName")
            or clip.get("filename")
            or clip.get("ClipName")
            or clip.get("clipName")
        )

        raw_label = clean_text(
            clip.get("Label")
            or clip.get("label")
            or clip.get("Angle")
            or clip.get("angle")
            or clip.get("Camera")
            or clip.get("camera")
            or clip.get("CameraName")
            or clip.get("cameraName")
        )

        if clip_name:
            normalized_name = _normalized_media_key(clip_name)
            basename = normalized_name.rsplit("/", 1)[-1]
            label = normalize_angle_label(
                raw_label
                or _angle_name_from_media_name(clip_name)
                or f"Video {clip_index}"
            )
            clip_label_by_name[normalized_name] = label
            clip_label_by_name[basename] = label
            clip_order.append((clip_name, label, clip))

    # Store by normalized media filename, NOT URL.  SasMap and MediaMap can
    # describe the same file with signed vs unsigned URLs.
    candidates = {}

    def add_candidate(media_name, label, url):
        media_name = clean_text(media_name)
        url = clean_text(url)

        if not url:
            return

        normalized_name = _normalized_media_key(media_name)
        basename = normalized_name.rsplit("/", 1)[-1]

        identity = (
            basename
            or normalized_media_identity(url)
            or url.lower()
        )

        resolved_label = normalize_angle_label(
            label
            or clip_label_by_name.get(normalized_name)
            or clip_label_by_name.get(basename)
            or _angle_name_from_media_name(media_name)
            or "Video"
        )

        current = candidates.get(identity)

        if current is None:
            candidates[identity] = {
                "angle_name": resolved_label,
                "video_url": url,
                "_media_name": media_name,
            }
            return

        # Preserve the explicit clip label if one becomes available later.
        if (
            current.get("angle_name") in {"", "VIDEO", "UNKNOWN"}
            and resolved_label
        ):
            current["angle_name"] = resolved_label

        current["video_url"] = _prefer_media_url(
            current.get("video_url"),
            url,
        )

    # PASS 1: explicit play Clips.
    for clip_name, label, clip in clip_order:
        url = _clip_direct_url(clip)

        if not url:
            url = (
                map_lookup(sas_map, clip_name)
                or map_lookup(media_map, clip_name)
            )

        if url:
            add_candidate(
                clip_name,
                label,
                url,
            )

    # PASS 2: match-wide maps grouped by embedded PLAY ###.
    #
    # MediaMap is scanned first and SasMap second so a signed SasMap URL can
    # replace the corresponding unsigned MediaMap URL when available.
    if play_number:
        for mapping in (media_map, sas_map):
            for media_name, url in _media_entry_items(mapping):
                if (
                    _play_number_from_media_name(media_name)
                    != play_number
                ):
                    continue

                normalized_name = _normalized_media_key(media_name)
                basename = normalized_name.rsplit("/", 1)[-1]

                label = (
                    clip_label_by_name.get(normalized_name)
                    or clip_label_by_name.get(basename)
                    or _angle_name_from_media_name(media_name)
                )

                add_candidate(
                    media_name,
                    label,
                    url,
                )

    angles = [
        {
            "angle_name": clean_text(item.get("angle_name")) or "Video",
            "video_url": clean_text(item.get("video_url")),
        }
        for item in candidates.values()
        if clean_text(item.get("video_url"))
    ]

    # If DV Sport ever supplies duplicate generic labels, keep every media
    # file by numbering only the repeated display names.
    label_totals = {}
    for angle in angles:
        base = clean_text(angle.get("angle_name")) or "Video"
        label_totals[base] = label_totals.get(base, 0) + 1

    label_seen = {}
    for angle in angles:
        base = clean_text(angle.get("angle_name")) or "Video"
        label_seen[base] = label_seen.get(base, 0) + 1

        if (
            label_totals[base] > 1
            and label_seen[base] > 1
        ):
            angle["angle_name"] = (
                f"{base} {label_seen[base]}"
            )

    angles.sort(
        key=_video_angle_sort_key
    )

    return angles[:30]


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
    Build a POI identity that does not depend on the playlist snapshot.

    DV Sport can republish a POI cutup with a different playlist ID and a
    different source PlayId.  The match play number is stable, so use it
    first.  Source IDs are only fallbacks for unusually incomplete data.
    """
    parsed = parse_poi_playlist_title(
        library_item.get("Title")
    )

    play_number = source_play_number(
        fields,
        play,
    )

    canonical = canonical_match_play_id(
        "poi",
        library_item.get("_Conference", ""),
        parsed.get("date"),
        parsed.get("match"),
        play_number,
    )

    if canonical:
        return canonical

    internal_play_id = (
        clean_text(play.get("InternalPlayId"))
        or clean_text(play.get("internalPlayId"))
    )

    if internal_play_id:
        return f"poi:internal:{internal_play_id}"

    play_id = (
        clean_text(play.get("PlayId"))
        or clean_text(play.get("playId"))
    )

    if play_id:
        return f"poi:play:{play_id}"

    raw = "|".join(
        [
            normalize_identity_text(
                library_item.get("_Conference", "")
            ),
            (
                parsed["date"].isoformat()
                if parsed.get("date")
                else ""
            ),
            normalize_identity_text(parsed.get("match")),
            normalized_play_number(play_number),
            clean_text(fields.get("SET")),
            clean_text(fields.get("Home")),
            clean_text(fields.get("Away")),
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

            "_sync_play_number":
                source_play_number(
                    fields,
                    play,
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

            "dvsport_crs_category":
                (
                    clean_text(fields.get("CRS CATEGORY"))
                    or clean_text(fields.get("CATEGORY"))
                    or review_type
                    or None
                ),

            "dvsport_play_category":
                (
                    clean_text(fields.get("PLAY CATEGORY"))
                    or clean_text(fields.get("CATEGORY"))
                    or None
                ),

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

        record["video_urls"] = extract_video_angles(
            root_data,
            playlist,
            play,
        )

        records.append(record)

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

            "_sync_play_number":
                source_play_number(
                    fields,
                    play,
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

            "dvsport_crs_category":
                None,

            "dvsport_play_category":
                (
                    clean_text(fields.get("PLAY CATEGORY"))
                    or clean_text(fields.get("POI TYPE"))
                    or clean_text(fields.get("CATEGORY"))
                    or clean_text(fields.get("DESCRIPTION"))
                    or None
                ),

            "challenge_result":
                None,

            "challenge_length_seconds":
                None,
        }

        record["video_urls"] = extract_video_angles(
            root_data,
            playlist,
            play,
        )

        records.append(record)

    return records


# ============================================================

# ============================================================
# FAULT PLAYLISTS
# ============================================================

def parse_fault_playlist_title(title):
    """
    Best-effort FAULT playlist title parsing.

    FAULT discovery does not depend on a particular playlist title.
    If the title contains the standard DV Sport leading date, use it.
    Match/date can also be recovered from the media URLs after the
    playlist is opened.
    """
    text = clean_text(title)

    result = {
        "date":
            parse_leading_date(text),
        "match":
            text,
    }

    patterns = [
        (
            r"^\d{2}[.\-]\d{2}[.\-]\d{2}\s*-\s*"
            r"(?P<match>.+?)"
            r"\s*-\s*FAULTS?"
            r"(?:\s*-\s*PLAY\s+\d+)?"
            r"(?:\s*-\s*\d{2}-\d{2}-\d{2})?$"
        ),
        (
            r"^(?P<match>.+?)"
            r"\s*-\s*FAULTS?"
            r"(?:\s*-\s*PLAY\s+\d+)?$"
        ),
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        parsed_match = clean_text(
            match.groupdict().get(
                "match"
            )
        )

        if parsed_match:
            result[
                "match"
            ] = parsed_match

        break

    return result


def fault_match_info_from_media(
    root_data,
):
    """
    Recover match and date from the real media URLs.

    Supplied DV Sport FAULT media paths follow a pattern such as:

      .../INDIANA VS NOTRE DAME - 08.14.26 - 17-41-35//
      PLAY 021 - PGM...

    This is used as a fallback when the FAULTS playlist title itself
    does not provide a usable date/match.
    """
    playlist = (
        root_data.get(
            "Playlist"
        )
        or root_data.get(
            "playlist"
        )
        or {}
    )

    maps = [
        playlist.get(
            "MediaMap"
        ),
        playlist.get(
            "mediamap"
        ),
        root_data.get(
            "SasMap"
        ),
        root_data.get(
            "sasMap"
        ),
    ]

    urls = []

    for mapping in maps:
        if not isinstance(
            mapping,
            dict,
        ):
            continue

        for value in mapping.values():
            url = clean_text(
                value
            )

            if url:
                urls.append(
                    url
                )

    pattern = re.compile(
        (
            r"/(?P<match>[^/]+?)"
            r"\s*-\s*"
            r"(?P<date>\d{2}[.\-]\d{2}[.\-]\d{2})"
            r"\s*-\s*"
            r"\d{2}-\d{2}-\d{2}"
            r"//PLAY\s+\d+"
        ),
        flags=re.IGNORECASE,
    )

    for url in urls:
        candidate = (
            url
            .replace(
                "%20",
                " ",
            )
        )

        match = pattern.search(
            candidate
        )

        if not match:
            continue

        raw_date = (
            match.group(
                "date"
            )
            .replace(
                "-",
                ".",
            )
        )

        try:
            match_date = datetime.strptime(
                raw_date,
                "%m.%d.%y",
            ).date()

        except ValueError:
            match_date = None

        return {
            "date":
                match_date,
            "match":
                clean_text(
                    match.group(
                        "match"
                    )
                ),
        }

    return {
        "date":
            None,
        "match":
            "",
    }


def resolve_fault_match_info(
    root_data,
    library_item,
):
    title_info = parse_fault_playlist_title(
        library_item.get(
            "Title"
        )
    )

    media_info = fault_match_info_from_media(
        root_data
    )

    return {
        "date":
            (
                title_info.get(
                    "date"
                )
                or media_info.get(
                    "date"
                )
            ),
        "match":
            (
                media_info.get(
                    "match"
                )
                or title_info.get(
                    "match"
                )
                or clean_text(
                    library_item.get(
                        "Title"
                    )
                )
                or "FAULTS"
            ),
    }


def fault_match_key(item):
    """
    Group republished FAULTS snapshots for the same match together.
    """
    parsed = parse_fault_playlist_title(
        item.get("Title")
    )

    match_date = parsed.get("date")
    match_name = normalize_identity_text(
        parsed.get("match")
    )

    if match_date and match_name:
        return (
            item.get("_Conference", ""),
            match_date.isoformat(),
            match_name,
        )

    # Extremely unusual title with no usable date/match: keep it isolated.
    return (
        item.get("_Conference", ""),
        "",
        normalize_identity_text(
            item.get("Id") or item.get("Url")
        ),
    )


def find_fault_playlist_groups(
    items,
    start_date,
    end_date,
):
    """
    Discover FAULT playlists and collapse republished snapshots by match.

    Actual DV Sport structure:
      HOME/VIDEOS/<YEAR>/<CONFERENCE>/FAULTS/<playlist>.DVPLAYLIST

    Multiple FAULTS playlists for one match are snapshots, not separate
    logical sources.  They are grouped here so only the best snapshot is
    imported later.
    """
    groups = {}

    for item in items:
        item_id = clean_text(item.get("Id"))
        url = clean_text(item.get("Url"))
        title = clean_text(item.get("Title"))

        conference = conference_from_id(item_id)

        if conference is None:
            continue

        expected_prefix = (
            f"HOME/VIDEOS/{YEAR}/"
            f"{conference}/FAULTS/"
        )

        if not item_id.upper().startswith(
            expected_prefix.upper()
        ):
            continue

        if item.get("Type") != 0:
            continue

        if not url.upper().endswith(".DVPLAYLIST"):
            continue

        title_date = parse_leading_date(title)

        if (
            title_date is not None
            and not (start_date <= title_date <= end_date)
        ):
            continue

        copy = dict(item)
        copy["_Conference"] = conference
        copy["_SourceType"] = "Fault"

        key = fault_match_key(copy)

        if key not in groups:
            groups[key] = {
                "combined": [],
                "individual": [],
            }

        groups[key]["combined"].append(copy)

    # Prefer the fullest snapshot, then the newest snapshot.
    for group in groups.values():
        group["combined"].sort(
            key=lambda item: (
                to_int(item.get("NumberOfPlays")) or -1,
                to_int(item.get("LastModifiedTicks")) or 0,
            ),
            reverse=True,
        )

    return groups


def build_fault_dvsport_id(
    fields,
    play,
    library_item,
    match_info=None,
):
    """
    Build a FAULT identity that survives playlist republishing.
    """
    match_info = match_info or parse_fault_playlist_title(
        library_item.get("Title")
    )

    play_number = source_play_number(
        fields,
        play,
    )

    canonical = canonical_match_play_id(
        "fault",
        library_item.get("_Conference", ""),
        match_info.get("date"),
        match_info.get("match"),
        play_number,
    )

    if canonical:
        return canonical

    internal_play_id = (
        clean_text(play.get("InternalPlayId"))
        or clean_text(play.get("internalPlayId"))
    )

    if internal_play_id:
        return f"fault:internal:{internal_play_id}"

    play_id = (
        clean_text(play.get("PlayId"))
        or clean_text(play.get("playId"))
    )

    if play_id:
        return f"fault:play:{play_id}"

    raw = "|".join(
        [
            normalize_identity_text(
                library_item.get("_Conference", "")
            ),
            (
                match_info["date"].isoformat()
                if isinstance(match_info.get("date"), date)
                else clean_text(match_info.get("date"))
            ),
            normalize_identity_text(match_info.get("match")),
            normalized_play_number(play_number),
            clean_text(fields.get("SET")),
            clean_text(fields.get("Home")),
            clean_text(fields.get("Away")),
        ]
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]

    return f"fault:fallback:{digest}"


def extract_faults_from_playlist(
    root_data,
    library_item,
    start_date=None,
    end_date=None,
):
    """
    Parse the actual DV Sport FAULT playlist schema.

    Confirmed headings include:
      SET
      PLAY_#
      Home
      Away
      FAULT
      FAULT TEAM
      REFEREE
      PLAYER #
      COMMENTS

    The DV Sport FAULT value is stored as source metadata in:
      dvsport_play_category

    Reviewer play_category remains untouched.
    """
    playlist = (
        root_data.get(
            "Playlist"
        )
        or root_data.get(
            "playlist"
        )
        or {}
    )

    match_info = resolve_fault_match_info(
        root_data,
        library_item,
    )

    match_date = match_info.get(
        "date"
    )

    if (
        match_date is not None
        and start_date is not None
        and end_date is not None
        and not (
            start_date
            <= match_date
            <= end_date
        )
    ):
        return []

    conference = library_item.get(
        "_Conference",
        "",
    )

    records = []

    plays = (
        playlist.get(
            "Plays"
        )
        or playlist.get(
            "plays"
        )
        or []
    )

    for play in plays:
        fields = fields_for_play(
            playlist,
            play,
        )

        home_score = clean_text(
            fields.get(
                "Home"
            )
        )

        away_score = clean_text(
            fields.get(
                "Away"
            )
        )

        score = (
            f"{home_score}-{away_score}"
            if (
                home_score
                or away_score
            )
            else ""
        )

        # This is the key correction:
        # the supplied playlist uses FAULT, not FAULT TYPE.
        fault_value = (
            clean_text(
                fields.get(
                    "FAULT"
                )
            )
            or clean_text(
                fields.get(
                    "FAULT TYPE"
                )
            )
            or clean_text(
                fields.get(
                    "PLAY CATEGORY"
                )
            )
            or clean_text(
                fields.get(
                    "CATEGORY"
                )
            )
            or None
        )

        record = {
            "dvsport_id":
                build_fault_dvsport_id(
                    fields,
                    play,
                    library_item,
                    match_info=match_info,
                ),

            "_sync_play_number":
                source_play_number(
                    fields,
                    play,
                ),

            "conference":
                conference,

            "match_date":
                (
                    match_date.isoformat()
                    if match_date
                    else None
                ),

            "match_name":
                (
                    clean_text(
                        match_info.get(
                            "match"
                        )
                    )
                    or clean_text(
                        library_item.get(
                            "Title"
                        )
                    )
                    or "FAULTS"
                ),

            "play_type":
                "Fault",

            "set_number":
                to_int(
                    fields.get(
                        "SET"
                    )
                ),

            "score":
                score,

            "challenging_team":
                None,

            "challenge_type":
                None,

            "dvsport_crs_category":
                None,

            "dvsport_play_category":
                fault_value,

            "challenge_result":
                None,

            "challenge_length_seconds":
                None,
        }

        record["video_urls"] = extract_video_angles(
            root_data,
            playlist,
            play,
        )

        records.append(record)

    return records


def load_fault_group_records(
    session,
    group,
    start_date=None,
    end_date=None,
):
    """
    Load one authoritative FAULTS snapshot for the match.

    Candidates are pre-sorted by NumberOfPlays and LastModifiedTicks.
    The first usable snapshot wins.  We intentionally do NOT merge every
    historical snapshot, which was one cause of duplicate FAULT imports.
    """
    errors = []

    candidates = (
        list(group.get("combined", []))
        + list(group.get("individual", []))
    )

    for item in candidates:
        try:
            root_data = get_playlist_data(
                session,
                item["Url"],
            )

            records = extract_faults_from_playlist(
                root_data,
                item,
                start_date=start_date,
                end_date=end_date,
            )

            if not records:
                continue

            deduped = {}

            for record in records:
                deduped[record["dvsport_id"]] = record

            return (
                list(deduped.values()),
                "snapshot",
                item,
                errors,
            )

        except Exception as exc:
            errors.append(
                {
                    "title": clean_text(item.get("Title")),
                    "error": str(exc),
                }
            )

    return (
        [],
        "snapshot",
        None,
        errors,
    )


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
            "id,dvsport_id,conference,match_date,match_name,play_type,"
            "set_number,score,dvsport_play_category,challenge_type,video_urls"
        )
        .eq("dvsport_id", dvsport_id)
        .limit(1)
        .execute()
    )

    return response.data[0] if response.data else None


def normalized_sync_play_type(value):
    text = normalize_identity_text(value)

    if text in {"CHALLENGE", "CHALLENGES"}:
        return "CHALLENGE"

    if text in {
        "POI",
        "POIS",
        "PLAY OF INTEREST",
        "PLAYS OF INTEREST",
    }:
        return "POI"

    if text in {"FAULT", "FAULTS"}:
        return "FAULT"

    return text


def existing_candidates_for_record(
    supabase,
    record,
):
    """
    Load a narrow same-day candidate set for duplicate matching.

    The query uses conference/date/set/score when available, then source
    type is normalized in Python so legacy values such as FAULT/FAULTS do
    not prevent a match.
    """
    conference = clean_text(record.get("conference"))
    match_date = clean_text(record.get("match_date"))
    incoming_type = normalized_sync_play_type(
        record.get("play_type")
    )

    if not conference or not match_date or not incoming_type:
        return []

    query = (
        supabase
        .table("plays")
        .select(
            "id,dvsport_id,conference,match_date,match_name,play_type,"
            "set_number,score,dvsport_play_category,challenge_type,video_urls"
        )
        .eq("conference", conference)
        .eq("match_date", match_date)
    )

    set_number = record.get("set_number")
    score = clean_text(record.get("score"))

    if set_number is not None:
        query = query.eq("set_number", set_number)

    if score:
        query = query.eq("score", score)

    response = query.execute()

    return [
        row
        for row in (response.data or [])
        if normalized_sync_play_type(
            row.get("play_type")
        ) == incoming_type
    ]



def secondary_existing_play_match(
    supabase,
    record,
):
    """
    Match an incoming play to legacy database rows even when dvsport_id
    changed between DV Sport playlist snapshots.

    Match priority:
      1. Any exact normalized media URL overlap.
      2. Same match + same PLAY ### recovered from stored media URLs.

    Both are substantially safer than matching on score alone.
    """
    candidates = existing_candidates_for_record(
        supabase,
        record,
    )

    if not candidates:
        return None, 0

    incoming_angles = record.get("video_urls") or []

    incoming_media = {
        normalized_media_identity(angle.get("video_url"))
        for angle in incoming_angles
        if isinstance(angle, dict)
        and normalized_media_identity(angle.get("video_url"))
    }

    incoming_play_number = normalized_play_number(
        record.get("_sync_play_number")
    )

    incoming_match = normalize_identity_text(
        record.get("match_name")
    )

    exact_media_matches = []
    play_number_matches = []

    for candidate in candidates:
        candidate_angles = candidate.get("video_urls") or []

        candidate_media = {
            normalized_media_identity(angle.get("video_url"))
            for angle in candidate_angles
            if isinstance(angle, dict)
            and normalized_media_identity(angle.get("video_url"))
        }

        if incoming_media and (
            incoming_media & candidate_media
        ):
            exact_media_matches.append(candidate)
            continue

        if not incoming_play_number:
            continue

        candidate_numbers = {
            normalized_play_number(
                play_number_from_media_url(
                    angle.get("video_url")
                )
            )
            for angle in candidate_angles
            if isinstance(angle, dict)
        }
        candidate_numbers.discard("")

        if (
            incoming_play_number in candidate_numbers
            and incoming_match
            and incoming_match
            == normalize_identity_text(
                candidate.get("match_name")
            )
        ):
            play_number_matches.append(candidate)

    matches = (
        exact_media_matches
        if exact_media_matches
        else play_number_matches
    )

    if not matches:
        return None, 0

    # If old bad syncs already produced duplicates, do not create another.
    # Pick one deterministic keeper without deleting reviewer data from any
    # existing row. Existing duplicate cleanup can be handled separately.
    matches.sort(
        key=lambda row: str(row.get("id", ""))
    )

    return matches[0], len(matches)



def _normalize_stored_video_list(value):
    """
    Normalize plays.video_urls into the standard list-of-dicts shape.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = []

    if isinstance(value, dict):
        value = [
            {
                "angle_name": name,
                "video_url": url,
            }
            for name, url in value.items()
        ]

    if not isinstance(value, list):
        return []

    result = []

    for index, item in enumerate(value[:30], start=1):
        if not isinstance(item, dict):
            continue

        url = clean_text(
            item.get("video_url")
            or item.get("url")
        )

        if not url:
            continue

        name = clean_text(
            item.get("angle_name")
            or item.get("name")
        ) or f"Video {index}"

        result.append(
            {
                "angle_name": normalize_angle_label(name),
                "video_url": url,
            }
        )

    return result


def merge_video_urls(
    existing_value,
    incoming_value,
):
    """
    Merge video URLs for the SAME play without allowing an older/sparser
    DV Sport snapshot to erase angles already discovered.

    Incoming URLs win for the same named camera, so refreshed/signed URLs
    are updated.  Existing cameras absent from a later sparse snapshot are
    retained.  This is especially important for Review-by-Game snapshots,
    where multiple historical versions of one match may be discovered.
    """
    existing = _normalize_stored_video_list(existing_value)
    incoming = _normalize_stored_video_list(incoming_value)

    merged = {}
    insertion_order = []

    def identity(angle):
        name = clean_text(angle.get("angle_name")).upper()
        if name:
            return f"name:{name}"

        media_id = normalized_media_identity(
            angle.get("video_url")
        )
        return f"url:{media_id}"

    for angle in existing:
        key = identity(angle)
        if key not in merged:
            insertion_order.append(key)
        merged[key] = angle

    # Overlay current DV Sport data so the newest URL wins for each camera.
    for angle in incoming:
        key = identity(angle)
        if key not in merged:
            insertion_order.append(key)
        merged[key] = angle

    result = [
        merged[key]
        for key in insertion_order
        if key in merged
    ]

    result.sort(
        key=_video_angle_sort_key
    )

    return result[:30]

def upsert_play(
    supabase,
    record,
):
    """
    Upsert without creating duplicate Challenge, POI, or FAULT rows.

    Manual review/tagging fields are never part of the write payload.
    """
    incoming_dvsport_id = record["dvsport_id"]

    existing = get_existing_play(
        supabase,
        incoming_dvsport_id,
    )

    matched_by_secondary_identity = False
    existing_match_count = 0

    if not existing:
        (
            existing,
            existing_match_count,
        ) = secondary_existing_play_match(
            supabase,
            record,
        )

        matched_by_secondary_identity = (
            existing is not None
        )

    database_record = public_database_record(
        record
    )

    if existing:
        # Never let a sparse/older DV Sport snapshot erase richer media
        # already stored for the same play. Incoming URLs refresh matching
        # camera names; existing cameras missing from this snapshot remain.
        database_record["video_urls"] = merge_video_urls(
            existing.get("video_urls"),
            database_record.get("video_urls"),
        )
        # If this was matched through media/play-number identity, writing
        # the incoming canonical dvsport_id migrates the legacy row in
        # place.  The exact-ID lookup above already proved the canonical
        # ID is not assigned to another row.
        (
            supabase
            .table("plays")
            .update(database_record)
            .eq("id", existing["id"])
            .execute()
        )

        return (
            existing["id"],
            "updated",
            matched_by_secondary_identity,
            existing_match_count,
        )

    response = (
        supabase
        .table("plays")
        .insert(database_record)
        .execute()
    )

    if response.data:
        return (
            response.data[0]["id"],
            "inserted",
            False,
            0,
        )

    inserted = get_existing_play(
        supabase,
        database_record["dvsport_id"],
    )

    if not inserted:
        raise RuntimeError(
            "Inserted play could not be read back from Supabase."
        )

    return (
        inserted["id"],
        "inserted",
        False,
        0,
    )


def import_records(
    supabase,
    records,
):
    """
    Insert/update plays with their named DV Sport video URLs stored directly
    in plays.video_urls. There is no separate video table.
    """
    result = {
        "inserted": 0,
        "updated": 0,
        "duplicates_prevented": 0,
        "existing_duplicate_rows_detected": 0,
        "video_clips_attached": 0,
    }

    for record in records:
        (
            _play_id,
            action,
            matched_secondary,
            existing_match_count,
        ) = upsert_play(
            supabase,
            record,
        )

        result[action] += 1

        if matched_secondary:
            result["duplicates_prevented"] += 1

        if existing_match_count > 1:
            result[
                "existing_duplicate_rows_detected"
            ] += existing_match_count - 1

        video_urls = record.get("video_urls") or []
        if isinstance(video_urls, list):
            result["video_clips_attached"] += len(video_urls)

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

    for record in all_records:
        deduped[
            record["dvsport_id"]
        ] = record

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

    fault_groups = (
        find_fault_playlist_groups(
            library_items,
            start_date,
            end_date,
        )
    )

    total_work = (
        len(challenge_playlists)
        + len(poi_groups)
        + len(fault_groups)
    )

    emit_progress(
        progress_callback,
        0.10,
        "Library scan complete",
        (
            f"{start_date:%m/%d/%Y} through {end_date:%m/%d/%Y}: "
            f"found {len(challenge_playlists):,} challenge "
            f"match playlist(s) and {len(poi_groups):,} "
            "match group(s) containing POIs and "
            f"{len(fault_groups):,} match group(s) containing FAULTS."
        ),
        challenge_playlists=
            len(challenge_playlists),
        poi_match_groups=
            len(poi_groups),
        fault_match_groups=
            len(fault_groups),
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

        "fault_match_groups":
            len(fault_groups),

        "challenges_found":
            0,

        "pois_found":
            0,

        "faults_found":
            0,

        "plays_inserted":
            0,

        "plays_updated":
            0,

        "duplicates_prevented":
            0,

        "existing_duplicate_rows_detected":
            0,

        "video_clips_attached":
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
            faults_found=
                summary["faults_found"],
            plays_inserted=
                summary["plays_inserted"],
            plays_updated=
                summary["plays_updated"],
            duplicates_prevented=
                summary["duplicates_prevented"],
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

            summary[
                "duplicates_prevented"
            ] += imported[
                "duplicates_prevented"
            ]

            summary[
                "existing_duplicate_rows_detected"
            ] += imported[
                "existing_duplicate_rows_detected"
            ]

            summary["video_clips_attached"] += imported[
                "video_clips_attached"
            ]

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
            faults_found=
                summary["faults_found"],
            plays_inserted=
                summary["plays_inserted"],
            plays_updated=
                summary["plays_updated"],
            duplicates_prevented=
                summary["duplicates_prevented"],
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

            summary[
                "duplicates_prevented"
            ] += imported[
                "duplicates_prevented"
            ]

            summary[
                "existing_duplicate_rows_detected"
            ] += imported[
                "existing_duplicate_rows_detected"
            ]

            summary["video_clips_attached"] += imported[
                "video_clips_attached"
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


    # --------------------------------------------------------
    # FAULTS
    # --------------------------------------------------------

    for key, group in sorted(fault_groups.items(), key=lambda pair: pair[0]):
        completed_work += 1
        conference = key[0]

        candidates = (
            group.get("combined", [])
            + group.get("individual", [])
        )

        fault_title = (
            clean_text(
                candidates[0].get("Title")
            )
            if candidates
            else "FAULTS"
        )

        fraction = 0.10 + 0.87 * ((completed_work - 1) / max(total_work, 1))

        emit_progress(
            progress_callback,
            fraction,
            "Syncing faults",
            f"{conference} • {fault_title}",
            current_item=completed_work,
            total_items=total_work,
            challenges_found=summary["challenges_found"],
            pois_found=summary["pois_found"],
            faults_found=summary["faults_found"],
            plays_inserted=summary["plays_inserted"],
            plays_updated=summary["plays_updated"],
            duplicates_prevented=summary["duplicates_prevented"],
        )

        try:
            records, source_mode, selected_combined, fault_errors = (
                load_fault_group_records(
                    session,
                    group,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            summary["faults_found"] += len(records)
            imported = import_records(supabase, records)
            summary["plays_inserted"] += imported["inserted"]
            summary["plays_updated"] += imported["updated"]
            summary["duplicates_prevented"] += imported["duplicates_prevented"]
            summary["existing_duplicate_rows_detected"] += imported[
                "existing_duplicate_rows_detected"
            ]
            summary["video_clips_attached"] += imported[
                "video_clips_attached"
            ]

            if not records and fault_errors:
                for error in fault_errors:
                    summary["errors"].append({
                        "type": "Fault",
                        "conference": conference,
                        "title": error["title"],
                        "error": error["error"],
                    })
        except Exception as exc:
            summary["errors"].append({
                "type": "Fault",
                "conference": conference,
                "title": fault_title,
                "error": str(exc),
            })

        time.sleep(REQUEST_DELAY_SECONDS)

    summary["elapsed_seconds"] = (
        time.time() - started
    )

    emit_progress(
        progress_callback,
        1.0,
        "Sync complete",
        (
            f"{summary['challenges_found']:,} challenges, "
            f"{summary['pois_found']:,} POIs, and "
            f"{summary['faults_found']:,} FAULTS processed."
        ),
        **summary,
    )

    return summary
