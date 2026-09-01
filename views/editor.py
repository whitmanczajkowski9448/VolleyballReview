import json

import pandas as pd
import requests
import streamlit as st
from datetime import date, datetime, timedelta

from services.database import get_supabase
from services.dvsport_media import fresh_video_url
from services.auth import require_admin, is_admin
from services.ui import (
    render_page_header,
    render_section_label,
    render_status_pill,
    render_empty,
)

from services.challenge_download import (
    render_challenge_download,
)
from services.challenge_email import (
    render_email_challenge_button,
)
from services.review_taxonomy import (
    NCAA_CHALLENGE_CATEGORIES,
    TOUCH_CONTEXTS,
    ORIGINAL_DECISIONS,
    CRS_OUTCOMES,
    PLAY_CATEGORIES,
)



# ============================================================
# PAGE
# ============================================================

require_admin()

render_page_header(
    "Tag / Edit",
    (
        "Review the DV Sport media attached to each play, "
        "classify challenges using the CRS structure, "
        "and track completion."
    ),
    eyebrow="NCAA WVB • REVIEW WORKSPACE",
)

supabase = get_supabase()


# ============================================================
# HELPERS
# ============================================================

def clean_value(
    value,
    fallback="—",
):
    if value is None:
        return fallback

    try:
        if pd.isna(value):
            return fallback
    except Exception:
        pass

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "null",
        "<na>",
    }:
        return fallback

    return value


def clean_text(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "null",
        "<na>",
    }:
        return ""

    return text



def normalized_play_type(value):
    text = clean_text(value).upper()

    if text in {
        "CHALLENGE",
        "CHALLENGES",
    }:
        return "Challenge"

    if text in {
        "POI",
        "POIS",
        "PLAY OF INTEREST",
        "PLAYS OF INTEREST",
    }:
        return "POI"

    if text in {
        "FAULT",
        "FAULTS",
    }:
        return "Fault"

    return clean_text(value) or "Unknown"


def normalized_review_status(value):
    text = clean_text(value)

    if not text:
        return "Not Viewed"

    lower = text.lower()

    if lower == "complete":
        return "Complete"

    if lower == "needs review":
        return "Needs Review"

    if lower == "not viewed":
        return "Not Viewed"

    return text


def normalize_outcome(play):
    raw = (
        clean_text(
            play.get("crs_outcome")
        )
        or clean_text(
            play.get("challenge_result")
        )
    )

    if not raw:
        return "Not Tagged"

    upper = raw.upper()

    if "REVER" in upper:
        return "Reversed"

    if "CONFIRM" in upper:
        return "Confirmed"

    if (
        "STAND" in upper
        or "INCONCLUSIVE" in upper
    ):
        return "Stands"

    if (
        "MECHANICAL" in upper
        or "VIDEO FAILURE" in upper
        or "VIDEO FAIL" in upper
    ):
        return "Mechanical / Video Failure"

    return raw


def challenge_category_for_queue(play):
    return (
        clean_text(
            play.get("ncaa_challenge_category")
        )
        or clean_text(
            play.get("crs_category")
        )
        or "Unclassified"
    )


def decision_accuracy_label(value):
    if value is True:
        return "Correct"

    if value is False:
        return "Incorrect"

    return "Not Tagged"


def training_label(value):
    return "Yes" if value is True else "No"


def involved_roles_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return [
            clean_text(item)
            for item in value
            if clean_text(item)
        ]

    text = clean_text(value)

    if not text:
        return []

    return [
        item.strip()
        for item in text.split(",")
        if item.strip()
    ]


def involved_roles_label(value):
    roles = involved_roles_list(value)

    return (
        ", ".join(roles)
        if roles
        else "Not Tagged"
    )


def usability_label(value):
    return "Unusable" if value is True else "Usable"


def date_value(value):
    parsed = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(parsed):
        return None

    return parsed.date()


def queue_row(play, number):
    play_type = normalized_play_type(
        play.get("play_type")
    )

    return {
        "Review": "Review →",
        "#": number,
        "Status": normalized_review_status(
            play.get("review_status")
        ),
        "Use": usability_label(
            play.get(
                "is_unusable"
            )
        ),
        "Date": clean_text(
            play.get("match_date")
        ),
        "Conference": clean_text(
            play.get("conference")
        ),
        "Match": clean_text(
            play.get("match_name")
        ),
        "Type": play_type,
        "Set": clean_value(
            play.get("set_number"),
            "",
        ),
        "Score": clean_text(
            play.get("score")
        ),
        "Challenging Team": clean_text(
            play.get("challenging_team")
        ),
        "Challenge Type": clean_text(
            play.get("challenge_type")
        ),
        "CRS Category": (
            challenge_category_for_queue(play)
            if play_type == "Challenge"
            else ""
        ),
        "Outcome": (
            normalize_outcome(play)
            if play_type == "Challenge"
            else ""
        ),
        "Decision Correct?": (
            decision_accuracy_label(
                play.get(
                    "review_decision_correct"
                )
            )
            if play_type == "Challenge"
            else ""
        ),
        "Training": (
            training_label(
                play.get(
                    "use_for_training"
                )
            )
            if play_type == "Challenge"
            else ""
        ),
        "Involved": (
            involved_roles_label(
                play.get(
                    "involved_roles"
                )
            )
            if play_type == "Challenge"
            else ""
        ),
    }



def parse_time_to_seconds(value):
    text = clean_text(value)

    if not text:
        return None

    if text.isdigit():
        return int(text)

    parts = text.split(":")

    try:
        parts = [
            int(part)
            for part in parts
        ]
    except ValueError:
        return None

    if len(parts) == 2:
        minutes, seconds = parts

        return (
            minutes * 60
            + seconds
        )

    if len(parts) == 3:
        hours, minutes, seconds = parts

        return (
            hours * 3600
            + minutes * 60
            + seconds
        )

    return None


def seconds_to_time(value):
    if value in (
        None,
        "",
    ):
        return ""

    try:
        total_seconds = int(value)
    except (
        ValueError,
        TypeError,
    ):
        return ""

    minutes = total_seconds // 60
    seconds = total_seconds % 60

    return (
        f"{minutes}:"
        f"{seconds:02d}"
    )


def initialize(
    key,
    value,
):
    """
    Initialize a widget/session-state value once for the selected play.

    Each review field uses a play-specific key, so moving between plays
    loads the stored database value without overwriting unsaved widget
    state on normal Streamlit reruns.
    """
    if key not in st.session_state:
        st.session_state[
            key
        ] = value


def has_usable_video_url(value):
    """
    Deliberately permissive DV Sport media check.

    If DV Sport supplied a nonblank value, let Streamlit attempt to
    render it. Do not reject signed URLs because of HEAD/Range/MIME
    behavior on the media server.
    """
    url = clean_text(value)

    if not url:
        return False

    return url.lower() not in {
        "none",
        "null",
        "nan",
        "<na>",
    }


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def video_url_is_playable(url):
    """
    Backward-compatible helper used by the page layout.

    We intentionally do NOT perform a network probe here. Signed DV
    Sport URLs can reject range requests or return unexpected MIME
    metadata even when the browser can play them successfully.
    """
    return has_usable_video_url(url)


def normalized_angle_name(value):
    return clean_text(value).upper()


def is_pgm(angle):
    return (
        normalized_angle_name(
            angle.get("angle_name")
        )
        == "PGM"
    )


def is_replay_output(angle):
    name = normalized_angle_name(
        angle.get("angle_name")
    )

    return name in {
        "REPLAY OUTPUT",
        "RO",
        "REPLAY",
    }


def video_sort_key(angle):
    if is_pgm(angle):
        return (0, "")

    if is_replay_output(angle):
        return (1, "")

    return (
        2,
        normalized_angle_name(
            angle.get("angle_name")
        ),
    )


def video_angles_from_play(play):
    """
    Return this play's named video angles using fresh FilmRoom SAS URLs.

    plays.video_urls keeps the stable DV Sport media reference. Each DV Sport
    blob URL is sent to FilmRoom's /VideoPlayer/GetSasUrl endpoint before use,
    so raw URLs become playable and expired SAS URLs are refreshed.
    """
    raw = play.get("video_urls")

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = []

    if isinstance(raw, dict):
        raw = [
            {"angle_name": name, "video_url": url}
            for name, url in raw.items()
        ]

    if not isinstance(raw, list):
        return []

    angles = []

    for index, item in enumerate(raw[:30], start=1):
        if not isinstance(item, dict):
            continue

        source_url = clean_text(
            item.get("video_url")
            or item.get("url")
            or item.get("source_url")
        )

        if not has_usable_video_url(source_url):
            continue

        name = (
            clean_text(item.get("angle_name") or item.get("name"))
            or f"Video {index}"
        )

        sas_error = ""
        try:
            playable_url = fresh_video_url(source_url)
        except Exception as exc:
            playable_url = source_url
            sas_error = str(exc)

        angles.append(
            {
                "id": index,
                "angle_name": name,
                "video_url": playable_url,
                "source_video_url": source_url,
                "media_name": clean_text(
                    item.get("media_name") or item.get("filename")
                ),
                "sas_error": sas_error,
            }
        )

    angles.sort(key=video_sort_key)
    return angles


def render_video_player(
    angle,
    primary=False,
):
    url = clean_text(
        angle.get("video_url")
    )

    if not has_usable_video_url(url):
        return

    angle_name = (
        clean_text(
            angle.get("angle_name")
        )
        or "Video"
    )

    if primary:
        st.subheader(angle_name)
    else:
        st.markdown(
            f"**{angle_name}**"
        )

    sas_error = clean_text(
        angle.get("sas_error")
    )

    if sas_error:
        st.warning(
            (
                "Could not refresh this DV Sport video's signed URL. "
                f"{sas_error}"
            ),
            icon="⚠️",
        )

    st.video(url)

    if url.lower().startswith(
        (
            "http://",
            "https://",
        )
    ):
        st.link_button(
            "Open Video",
            url,
            use_container_width=True,
        )



# ============================================================
# LOAD PLAYS
# ============================================================

try:
    response = (
        supabase
        .table("plays")
        .select("*")
        .order(
            "match_date",
            desc=True,
        )
        .execute()
    )

    plays = response.data or []

except Exception as exc:
    st.error(
        "Could not load plays."
    )
    st.exception(exc)
    st.stop()


if not plays:
    render_empty(
        "No plays are available yet."
    )
    st.stop()


# ============================================================
# SIMPLE PLAY BROWSER
# ============================================================

render_section_label(
    "Choose a Play"
)

# plays is already a list returned by Supabase.

# Normalize once for filtering and display.
for item in plays:
    item["_queue_play_type"] = normalized_play_type(
        item.get("play_type")
    )
    item["_queue_unusable"] = bool(
        item.get("is_unusable")
    )
    item["_queue_status"] = normalized_review_status(
        item.get("review_status")
    )
    item["_queue_outcome"] = normalize_outcome(item)
    item["_queue_category"] = challenge_category_for_queue(item)
    item["_queue_accuracy"] = decision_accuracy_label(
        item.get("review_decision_correct")
    )
    item["_queue_training"] = training_label(
        item.get("use_for_training")
    )
    item["_queue_involved_roles"] = involved_roles_list(
        item.get("involved_roles")
    )
    item["_queue_date"] = date_value(
        item.get("match_date")
    )


conferences = sorted({
    clean_text(item.get("conference"))
    for item in plays
    if clean_text(item.get("conference"))
})

challenge_types = sorted({
    clean_text(item.get("challenge_type"))
    for item in plays
    if (
        item["_queue_play_type"] == "Challenge"
        and clean_text(item.get("challenge_type"))
    )
})

crs_categories = sorted({
    item["_queue_category"]
    for item in plays
    if (
        item["_queue_play_type"] == "Challenge"
        and item["_queue_category"]
    )
})

outcomes = sorted({
    item["_queue_outcome"]
    for item in plays
    if (
        item["_queue_play_type"] == "Challenge"
        and item["_queue_outcome"]
    )
})

challenging_teams = sorted({
    clean_text(item.get("challenging_team"))
    for item in plays
    if (
        item["_queue_play_type"] == "Challenge"
        and clean_text(item.get("challenging_team"))
    )
})

INVOLVED_ROLE_OPTIONS = [
    "R1",
    "R2",
    "Line Judge",
    "Coach",
    "Player",
    "Scorer / Table",
    "Review Official / Technician",
    "Other",
]

valid_dates = [
    item["_queue_date"]
    for item in plays
    if item["_queue_date"] is not None
]

min_data_date = min(valid_dates) if valid_dates else date.today()
max_data_date = max(valid_dates) if valid_dates else date.today()


# The normal page is intentionally simple. All detailed filters live here.
with st.expander(
    "Advanced Filters",
    expanded=False,
):
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        play_type_filter = st.selectbox(
            "Play Type",
            ["All", "Challenge", "POI", "Fault"],
            index=["All", "Challenge", "POI", "Fault"].index("Challenge"),
            key="editor_filter_play_type",
        )

    with f2:
        conference_filter = st.selectbox(
            "Conference",
            ["All"] + conferences,
            key="editor_filter_conference",
        )

    with f3:
        status_filter = st.selectbox(
            "Review Status",
            [
                "All",
                "Not Viewed",
                "Needs Review",
                "Complete",
            ],
            key="editor_filter_status",
        )

    with f4:
        record_use_filter = st.selectbox(
            "Record Use",
            [
                "Usable Only",
                "All Records",
                "Unusable Only",
            ],
            key="editor_filter_record_use",
        )

    d1, d2, d3 = st.columns([1.0, 1.0, 2.0])

    with d1:
        date_filter = st.selectbox(
            "Date Range",
            [
                "All Dates",
                "Last 7 Days",
                "Custom",
            ],
            key="editor_filter_date_mode",
        )

    filter_start_date = None
    filter_end_date = None

    if date_filter == "Last 7 Days":
        filter_end_date = date.today()
        filter_start_date = filter_end_date - timedelta(days=7)

    elif date_filter == "Custom":
        with d2:
            filter_start_date = st.date_input(
                "Start Date",
                value=min_data_date,
                key="editor_filter_start_date",
            )

        with d3:
            filter_end_date = st.date_input(
                "End Date",
                value=max_data_date,
                key="editor_filter_end_date",
            )

        if filter_start_date > filter_end_date:
            st.error("Start Date cannot be after End Date.")
            st.stop()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        challenge_type_filter = st.selectbox(
            "DV Sport Challenge Type",
            ["All"] + challenge_types,
            key="editor_filter_challenge_type",
        )

    with c2:
        crs_category_filter = st.selectbox(
            "NCAA Challenge Category",
            ["All"] + crs_categories,
            key="editor_filter_crs_category",
        )

    with c3:
        outcome_filter = st.selectbox(
            "Challenge Outcome",
            ["All"] + outcomes,
            key="editor_filter_outcome",
        )

    with c4:
        challenging_team_filter = st.selectbox(
            "Challenging Team",
            ["All"] + challenging_teams,
            key="editor_filter_challenging_team",
        )

    t1, t2, t3 = st.columns(3)

    with t1:
        accuracy_filter = st.selectbox(
            "Review Decision",
            [
                "All",
                "Correct",
                "Incorrect",
                "Not Tagged",
            ],
            key="editor_filter_accuracy",
        )

    with t2:
        training_filter = st.selectbox(
            "Training Use",
            [
                "All",
                "Marked for Training",
                "Not Marked",
            ],
            key="editor_filter_training",
        )

    with t3:
        involved_filter = st.selectbox(
            "Who Was Involved",
            ["All"] + INVOLVED_ROLE_OPTIONS,
            key="editor_filter_involved",
        )

    search_filter = st.text_input(
        "Search Match / Team / Score / Notes",
        placeholder=(
            "Type part of a match, team, score, category, or note..."
        ),
        key="editor_filter_search",
    )

    if st.button(
        "Reset Filters",
        key="editor_reset_filters",
    ):
        for state_key in list(st.session_state.keys()):
            if state_key.startswith("editor_filter_"):
                st.session_state.pop(state_key, None)

        st.session_state.pop("editor_match_picker", None)
        st.session_state.pop("editor_play_picker", None)
        st.rerun()


# ============================================================
# APPLY FILTERS
# ============================================================

filtered_plays = []
search_term = clean_text(search_filter).lower()

for item in plays:
    if (
        record_use_filter == "Usable Only"
        and item["_queue_unusable"]
    ):
        continue

    if (
        record_use_filter == "Unusable Only"
        and not item["_queue_unusable"]
    ):
        continue

    if (
        play_type_filter != "All"
        and item["_queue_play_type"] != play_type_filter
    ):
        continue

    if (
        conference_filter != "All"
        and clean_text(item.get("conference")) != conference_filter
    ):
        continue

    if (
        status_filter != "All"
        and item["_queue_status"] != status_filter
    ):
        continue

    item_date = item["_queue_date"]

    if (
        filter_start_date is not None
        and (
            item_date is None
            or item_date < filter_start_date
        )
    ):
        continue

    if (
        filter_end_date is not None
        and (
            item_date is None
            or item_date > filter_end_date
        )
    ):
        continue

    if item["_queue_play_type"] == "Challenge":
        if (
            challenge_type_filter != "All"
            and clean_text(item.get("challenge_type")) != challenge_type_filter
        ):
            continue

        if (
            crs_category_filter != "All"
            and item["_queue_category"] != crs_category_filter
        ):
            continue

        if (
            outcome_filter != "All"
            and item["_queue_outcome"] != outcome_filter
        ):
            continue

        if (
            challenging_team_filter != "All"
            and clean_text(item.get("challenging_team")) != challenging_team_filter
        ):
            continue

        if (
            accuracy_filter != "All"
            and item["_queue_accuracy"] != accuracy_filter
        ):
            continue

        if (
            training_filter == "Marked for Training"
            and item["_queue_training"] != "Yes"
        ):
            continue

        if (
            training_filter == "Not Marked"
            and item["_queue_training"] != "No"
        ):
            continue

        if (
            involved_filter != "All"
            and involved_filter not in item["_queue_involved_roles"]
        ):
            continue

    if search_term:
        haystack = " ".join(
            [
                clean_text(item.get("match_name")),
                clean_text(item.get("conference")),
                clean_text(item.get("score")),
                clean_text(item.get("challenging_team")),
                clean_text(item.get("challenge_type")),
                clean_text(item.get("crs_category")),
                clean_text(item.get("crs_outcome")),
                clean_text(item.get("reviewer_notes")),
                clean_text(item.get("weekly_summary_note")),
                clean_text(item.get("involved_people")),
                clean_text(item.get("unusable_reason")),
                clean_text(item.get("unusable_notes")),
            ]
        ).lower()

        if search_term not in haystack:
            continue

    filtered_plays.append(item)


if not filtered_plays:
    render_empty(
        "No plays match the current filters. Open Advanced Filters to change them."
    )
    st.stop()


# ============================================================
# TWO-STEP BROWSER: MATCH -> PLAY
# ============================================================

def browser_match_key(item):
    return (
        clean_text(item.get("match_date")),
        clean_text(item.get("conference")),
        clean_text(item.get("match_name")),
    )


def browser_match_label(key, count):
    match_date_text, conference_text, match_text = key
    return (
        f"{match_date_text or 'No Date'}  •  "
        f"{conference_text or 'No Conference'}  •  "
        f"{match_text or 'Unnamed Match'}  "
        f"({count} play{'' if count == 1 else 's'})"
    )


def browser_play_label(item, position, total):
    play_type = item["_queue_play_type"]
    set_text = clean_text(item.get("set_number"))
    score_text = clean_text(item.get("score"))
    team_text = clean_text(item.get("challenging_team"))
    type_text = clean_text(item.get("challenge_type"))
    category_text = clean_text(item.get("crs_category"))
    status_text = item["_queue_status"]

    details = [
        f"{play_type.upper()} {position}/{total}",
    ]

    if set_text:
        details.append(f"Set {set_text}")
    if score_text:
        details.append(score_text)
    if team_text:
        details.append(team_text)
    if type_text:
        details.append(type_text)
    elif category_text:
        details.append(category_text)

    details.append(status_text)

    if item["_queue_unusable"]:
        details.append("UNUSABLE")

    return "  •  ".join(details)


match_to_plays = {}
match_keys = []

for item in filtered_plays:
    key = browser_match_key(item)

    if key not in match_to_plays:
        match_to_plays[key] = []
        match_keys.append(key)

    match_to_plays[key].append(item)


match_picker_key = "editor_match_picker"
play_picker_key = "editor_play_picker"

if st.session_state.get(match_picker_key) not in match_keys:
    current_id = st.session_state.get("editor_selected_play_id")
    current_match = None

    for item in filtered_plays:
        if item.get("id") == current_id:
            current_match = browser_match_key(item)
            break

    st.session_state[match_picker_key] = (
        current_match
        if current_match in match_keys
        else match_keys[0]
    )


browse1, browse2 = st.columns([1.1, 1.4])

with browse1:
    selected_match_key = st.selectbox(
        "Match",
        options=match_keys,
        key=match_picker_key,
        format_func=lambda key: browser_match_label(
            key,
            len(match_to_plays[key]),
        ),
    )

current_match_plays = match_to_plays[selected_match_key]
current_match_ids = [item["id"] for item in current_match_plays]

if st.session_state.get(play_picker_key) not in current_match_ids:
    st.session_state[play_picker_key] = current_match_ids[0]

play_by_id = {item["id"]: item for item in current_match_plays}
play_position = {
    item["id"]: index + 1
    for index, item in enumerate(current_match_plays)
}

with browse2:
    selected_play_id = st.selectbox(
        "Challenge / Play",
        options=current_match_ids,
        key=play_picker_key,
        format_func=lambda play_id: browser_play_label(
            play_by_id[play_id],
            play_position[play_id],
            len(current_match_ids),
        ),
    )

st.session_state["editor_selected_play_id"] = selected_play_id
play = play_by_id[selected_play_id]
play_id = play["id"]
is_challenge = play["_queue_play_type"] == "Challenge"

queue_ids = current_match_ids
selected_index = queue_ids.index(selected_play_id)

previous_play_id = (
    queue_ids[selected_index - 1]
    if selected_index > 0
    else None
)

next_play_id = (
    queue_ids[selected_index + 1]
    if selected_index < len(queue_ids) - 1
    else None
)


# ============================================================
# CURRENTLY VIEWING — MAKE THE ACTIVE CHALLENGE OBVIOUS
# ============================================================

with st.container(border=True):
    top_left, top_right = st.columns([4.8, 1.2])

    with top_left:
        st.caption("CURRENTLY VIEWING")
        st.markdown(
            f"## {clean_value(play.get('match_name'), 'Play')}"
        )

        identity_parts = [
            play["_queue_play_type"],
            f"{selected_index + 1} of {len(queue_ids)} in this match",
        ]

        if clean_text(play.get("set_number")):
            identity_parts.append(
                f"Set {clean_text(play.get('set_number'))}"
            )

        if clean_text(play.get("score")):
            identity_parts.append(
                f"Score {clean_text(play.get('score'))}"
            )

        if clean_text(play.get("challenging_team")):
            identity_parts.append(
                f"Challenge by {clean_text(play.get('challenging_team'))}"
            )

        st.markdown(
            "**" + "  •  ".join(identity_parts) + "**"
        )

        detail_parts = [
            clean_text(play.get("challenge_type")),
            clean_text(play.get("crs_category")),
            clean_text(play.get("crs_outcome")),
        ]
        detail_parts = [part for part in detail_parts if part]

        if detail_parts:
            st.caption("  •  ".join(detail_parts))

    with top_right:
        render_status_pill(
            play.get("review_status")
            or "Not Viewed"
        )


st.caption(
    f"{len(filtered_plays):,} play{'' if len(filtered_plays) == 1 else 's'} "
    f"across {len(match_keys):,} match{'' if len(match_keys) == 1 else 'es'} match the current filters."
)


# ============================================================
# TOP CHALLENGE DOWNLOAD
# ============================================================

top_video_angles = video_angles_from_play(play)


if is_challenge:
    action_download, action_email, action_space = st.columns(
        [
            1.35,
            1.35,
            2.3,
        ]
    )

    with action_download:
        render_challenge_download(
            play,
            top_video_angles,
            "editor",
        )

    with action_email:
        if is_admin():
            render_email_challenge_button(
                play,
                top_video_angles,
                supabase,
                "editor",
            )


# ============================================================
# PLAY INFORMATION
# ============================================================

st.divider()

title_col, status_col = st.columns(
    [
        5,
        1,
    ]
)

with title_col:
    st.subheader(
        clean_value(
            play.get("match_name"),
            "Play",
        )
    )

with status_col:
    render_status_pill(
        play.get("review_status")
        or "Not Viewed"
    )


info1, info2, info3, info4 = st.columns(
    4
)

with info1:
    st.caption("Conference")
    st.write(
        clean_value(
            play.get("conference")
        )
    )

with info2:
    st.caption("Date")
    st.write(
        clean_value(
            play.get("match_date")
        )
    )

with info3:
    st.caption("Set")
    st.write(
        clean_value(
            play.get("set_number")
        )
    )

with info4:
    st.caption("Score")
    st.write(
        clean_value(
            play.get("score")
        )
    )


# ============================================================
# VIDEO FOR THIS PLAY
# ============================================================

render_section_label(
    "Play Video"
)

video_angles = video_angles_from_play(play)


# CRITICAL:
# Completely remove missing/blank URL rows before
# creating columns or players.
video_angles = [
    angle
    for angle in video_angles
    if video_url_is_playable(
        clean_text(
            angle.get("video_url")
        )
    )
]

video_angles.sort(
    key=video_sort_key
)


if not video_angles:
    render_empty(
        "DV Sport does not have a video URL attached to this play."
    )

else:
    pgm = next(
        (
            angle
            for angle in video_angles
            if is_pgm(angle)
        ),
        None,
    )

    replay_output = next(
        (
            angle
            for angle in video_angles
            if is_replay_output(angle)
        ),
        None,
    )

    primary_ids = {
        angle["id"]
        for angle in [
            pgm,
            replay_output,
        ]
        if angle is not None
    }

    primary_angles = [
        angle
        for angle in [
            pgm,
            replay_output,
        ]
        if angle is not None
    ]


    if len(primary_angles) == 2:
        primary_left, primary_right = (
            st.columns(2)
        )

        with primary_left:
            render_video_player(
                primary_angles[0],
                primary=True,
            )

        with primary_right:
            render_video_player(
                primary_angles[1],
                primary=True,
            )

    elif len(primary_angles) == 1:
        render_video_player(
            primary_angles[0],
            primary=True,
        )


    secondary_angles = [
        angle
        for angle in video_angles
        if angle.get("id")
        not in primary_ids
    ]


    if secondary_angles:
        st.write("")
        st.caption(
            "ADDITIONAL ANGLES"
        )

        for start in range(
            0,
            len(secondary_angles),
            3,
        ):
            row_angles = (
                secondary_angles[
                    start:
                    start + 3
                ]
            )

            # Only create as many columns as real videos.
            columns = st.columns(
                len(row_angles)
            )

            for column, angle in zip(
                columns,
                row_angles,
            ):
                with column:
                    render_video_player(
                        angle,
                        primary=False,
                    )


# ============================================================
# ============================================================
# NCAA REVIEW TAXONOMY
# ============================================================

CRS_CATEGORIES = NCAA_CHALLENGE_CATEGORIES
REVIEW_STATUSES = [
    "Not Viewed",
    "Needs Review",
    "Complete",
]


# SESSION STATE
# ============================================================

category_key = (
    f"category_{play_id}"
)

play_category_key = (
    f"play_category_{play_id}"
)

play_category_other_key = (
    f"play_category_other_{play_id}"
)

starred_key = (
    f"starred_{play_id}"
)

touch_key = (
    f"touch_{play_id}"
)

decision_key = (
    f"decision_{play_id}"
)

outcome_key = (
    f"outcome_{play_id}"
)

changed_key = (
    f"changed_{play_id}"
)

length_key = (
    f"length_{play_id}"
)

notes_key = (
    f"notes_{play_id}"
)

weekly_key = (
    f"weekly_{play_id}"
)

status_key = (
    f"status_{play_id}"
)

accuracy_key = (
    f"accuracy_{play_id}"
)

training_key = (
    f"training_{play_id}"
)

involved_roles_key = (
    f"involved_roles_{play_id}"
)

involved_people_key = (
    f"involved_people_{play_id}"
)

unusable_key = (
    f"unusable_{play_id}"
)

unusable_reason_key = (
    f"unusable_reason_{play_id}"
)

unusable_notes_key = (
    f"unusable_notes_{play_id}"
)

initialize(
    category_key,
    play.get("ncaa_challenge_category")
    or play.get("crs_category")
    or "",
)

initialize(
    play_category_key,
    play.get("play_category")
    or "",
)

initialize(
    play_category_other_key,
    play.get("play_category_other")
    or "",
)

initialize(
    starred_key,
    bool(
        play.get("is_starred")
    ),
)

initialize(
    touch_key,
    play.get("crs_touch_context")
    or "",
)

initialize(
    decision_key,
    play.get("crs_original_decision")
    or "",
)

initialize(
    outcome_key,
    play.get("crs_outcome")
    or "",
)

initialize(
    changed_key,
    play.get(
        "crs_original_fault_changed"
    ),
)

initialize(
    length_key,
    seconds_to_time(
        play.get(
            "challenge_length_seconds"
        )
    ),
)

initialize(
    notes_key,
    play.get("reviewer_notes")
    or "",
)

initialize(
    weekly_key,
    play.get(
        "weekly_summary_note"
    )
    or "",
)

initialize(
    status_key,
    play.get("review_status")
    or "Not Viewed",
)

existing_accuracy = play.get(
    "review_decision_correct"
)

accuracy_default = (
    "Correct"
    if existing_accuracy is True
    else "Incorrect"
    if existing_accuracy is False
    else None
)

initialize(
    accuracy_key,
    accuracy_default,
)

initialize(
    training_key,
    bool(
        play.get(
            "use_for_training"
        )
    ),
)

initialize(
    involved_roles_key,
    involved_roles_list(
        play.get(
            "involved_roles"
        )
    ),
)

initialize(
    involved_people_key,
    play.get(
        "involved_people"
    )
    or "",
)

initialize(
    unusable_key,
    bool(
        play.get(
            "is_unusable"
        )
    ),
)

initialize(
    unusable_reason_key,
    play.get(
        "unusable_reason"
    )
    or "Technical Difficulty",
)

initialize(
    unusable_notes_key,
    play.get(
        "unusable_notes"
    )
    or "",
)


# ============================================================
# CRS CLASSIFICATION — CHALLENGES ONLY
# ============================================================

if is_challenge:
    render_section_label(
        "NCAA Challenge Classification"
    )

    dvsport_crs = (
        clean_text(
            play.get("dvsport_crs_category")
        )
        or clean_text(
            play.get("challenge_type")
        )
    )

    st.text_input(
        "DV Sport CRS / Source Category",
        value=dvsport_crs,
        disabled=True,
        help=(
            "Imported source metadata from DV Sport. "
            "This field is not changed by reviewer tagging."
        ),
    )

    category = st.selectbox(
        "NCAA Challenge Category",
        CRS_CATEGORIES,
        key=category_key,
    )

    if (
        category
        == "Ball contacting a player"
    ):
        touch_context = st.selectbox(
            "Touch Context",
            TOUCH_CONTEXTS,
            key=touch_key,
        )
    else:
        touch_context = ""

    decision_options = (
        ORIGINAL_DECISIONS.get(
            category,
            [""],
        )
    )

    if (
        st.session_state[
            decision_key
        ]
        not in decision_options
    ):
        st.session_state[
            decision_key
        ] = ""

    original_decision = st.selectbox(
        "Original Fault Decision",
        decision_options,
        key=decision_key,
    )

    challenge_outcome = st.selectbox(
        "Challenge Outcome",
        CRS_OUTCOMES,
        key=outcome_key,
    )

    changed_options = [
        "Not entered",
        "Yes",
        "No",
    ]

    existing_changed = (
        st.session_state[
            changed_key
        ]
    )

    if existing_changed is True:
        changed_default = "Yes"
    elif existing_changed is False:
        changed_default = "No"
    else:
        changed_default = (
            "Not entered"
        )

    changed_display_key = (
        f"changed_display_{play_id}"
    )

    initialize(
        changed_display_key,
        changed_default,
    )

    changed_display = st.radio(
        "Original Fault Decision Changed?",
        changed_options,
        horizontal=True,
        key=changed_display_key,
    )

    if changed_display == "Yes":
        original_fault_changed = True
    elif changed_display == "No":
        original_fault_changed = False
    else:
        original_fault_changed = None

    imported_length_seconds = (
        play.get(
            "challenge_length_seconds"
        )
    )

    if imported_length_seconds is not None:
        challenge_length = (
            seconds_to_time(
                imported_length_seconds
            )
        )

        st.text_input(
            "Length of Challenge",
            value=challenge_length,
            disabled=True,
            help=(
                "Imported automatically from "
                "DV Sport REVIEW TIME."
            ),
        )

        st.caption(
            "DV Sport source • read only"
        )

        current_length_seconds = int(
            imported_length_seconds
        )

    else:
        challenge_length = st.text_input(
            "Length of Challenge",
            key=length_key,
            placeholder="Example: 1:24",
            help=(
                "DV Sport did not provide REVIEW TIME "
                "for this challenge."
            ),
        )

        current_length_seconds = (
            parse_time_to_seconds(
                challenge_length
            )
        )

else:
    # POIs and FAULTS do not use challenge-only NCAA outcome fields.
    category = play.get(
        "crs_category"
    ) or ""

    touch_context = play.get(
        "crs_touch_context"
    ) or ""

    original_decision = play.get(
        "crs_original_decision"
    ) or ""

    challenge_outcome = play.get(
        "crs_outcome"
    ) or ""

    original_fault_changed = play.get(
        "crs_original_fault_changed"
    )

    current_length_seconds = play.get(
        "challenge_length_seconds"
    )


# ============================================================
# ============================================================
# PLAY CLASSIFICATION — ALL PLAY TYPES
# ============================================================

render_section_label(
    "Play Classification"
)

play_classification = st.selectbox(
    "Play / Fault Category",
    PLAY_CATEGORIES,
    key=play_category_key,
    help=(
        "Reviewer-controlled volleyball classification. "
        "Available for Challenges, POIs, and imported FAULTS."
    ),
)

if play_classification == "Other":
    play_classification_other = st.text_input(
        "Other Play Category",
        key=play_category_other_key,
        placeholder="Enter a short custom play/fault category",
    )
else:
    play_classification_other = ""

is_starred = st.checkbox(
    "★ Star this play",
    key=starred_key,
    help=(
        "Favorite this Challenge, POI, or FAULT so it can be "
        "quickly filtered and found later."
    ),
)

dvsport_play_category = clean_text(
    play.get("dvsport_play_category")
)

if dvsport_play_category:
    st.caption(
        f"DV Sport source category: {dvsport_play_category}"
    )


# RECORD USE — CHALLENGES ONLY
# ============================================================

if is_challenge:
    render_section_label(
        "Record Use"
    )

    is_unusable = st.checkbox(
        "Mark this challenge unusable",
        key=unusable_key,
        help=(
            "The record stays in the database and remains viewable, "
            "editable, downloadable, and emailable, but is excluded "
            "from all dashboard analysis and coordinator reports."
        ),
    )

    if is_unusable:
        st.warning(
            (
                "This challenge is excluded from all analysis "
                "and reports after you save."
            ),
            icon="⚠️",
        )

        unusable_reason = st.selectbox(
            "Reason",
            ['Technical Difficulty', 'Video / Media Unusable', 'Incomplete / Incorrect Record', 'Duplicate Record', 'Other / Not Usable'],
            key=unusable_reason_key,
        )

        unusable_notes = st.text_input(
            "Unusable Details",
            key=unusable_notes_key,
            placeholder=(
                "Optional: brief explanation of the technical issue "
                "or why this challenge should not be used"
            ),
        )

    else:
        unusable_reason = None
        unusable_notes = None

else:
    is_unusable = bool(
        play.get(
            "is_unusable"
        )
    )
    unusable_reason = play.get(
        "unusable_reason"
    )
    unusable_notes = play.get(
        "unusable_notes"
    )


# ============================================================
# RAPID REVIEW TAGS — CHALLENGES ONLY
# ============================================================

if is_challenge:
    render_section_label(
        "Rapid Review Tags"
    )

    st.caption(
        (
            "Quick post-match tags for review quality, "
            "training use, and who was involved."
        )
    )

    if hasattr(
        st,
        "segmented_control",
    ):
        accuracy_choice = st.segmented_control(
            "Was the review decision correct?",
            [
                "Correct",
                "Incorrect",
            ],
            key=accuracy_key,
            selection_mode="single",
        )
    else:
        fallback_key = (
            f"{accuracy_key}_fallback"
        )

        initialize(
            fallback_key,
            st.session_state.get(
                accuracy_key
            )
            or "Not Tagged",
        )

        accuracy_choice = st.radio(
            "Was the review decision correct?",
            [
                "Not Tagged",
                "Correct",
                "Incorrect",
            ],
            horizontal=True,
            key=fallback_key,
        )

    if accuracy_choice == "Correct":
        review_decision_correct = True
    elif accuracy_choice == "Incorrect":
        review_decision_correct = False
    else:
        review_decision_correct = None

    use_for_training = st.checkbox(
        "Mark for use in training",
        key=training_key,
        help=(
            "Marks this challenge so it can be filtered "
            "and collected for training later."
        ),
    )

    st.markdown(
        "**Who was involved in the play?**"
    )

    if hasattr(
        st,
        "pills",
    ):
        involved_roles = st.pills(
            "Involved Roles",
            INVOLVED_ROLE_OPTIONS,
            selection_mode="multi",
            key=involved_roles_key,
            label_visibility="collapsed",
        )

        involved_roles = (
            involved_roles
            or []
        )

    else:
        involved_roles = []
        existing_roles = set(
            st.session_state.get(
                involved_roles_key,
                []
            )
        )

        role_columns = st.columns(4)

        for role_index, role in enumerate(
            INVOLVED_ROLE_OPTIONS
        ):
            role_key = (
                f"{involved_roles_key}_"
                f"{role_index}"
            )

            with role_columns[
                role_index % 4
            ]:
                role_checked = st.checkbox(
                    role,
                    value=(
                        role in existing_roles
                    ),
                    key=role_key,
                )

            if role_checked:
                involved_roles.append(role)

    involved_people = st.text_input(
        "Names / Details",
        key=involved_people_key,
        placeholder=(
            "Optional: player number/name, official name, "
            "or another identifying detail"
        ),
    )

else:
    review_decision_correct = play.get(
        "review_decision_correct"
    )
    use_for_training = bool(
        play.get(
            "use_for_training"
        )
    )
    involved_roles = involved_roles_list(
        play.get(
            "involved_roles"
        )
    )
    involved_people = (
        play.get(
            "involved_people"
        )
        or ""
    )


# ============================================================
# NOTES
# ============================================================

render_section_label(
    "Reviewer Notes"
)

reviewer_notes = st.text_area(
    "General Reviewer Notes",
    key=notes_key,
    height=120,
)

weekly_summary_note = st.text_area(
    "Special Weekly Summary Note",
    key=weekly_key,
    height=100,
    help=(
        "Use this when you specifically want "
        "this play highlighted in the Monday report."
    ),
)


# ============================================================
# REVIEW WORKFLOW
# ============================================================

render_section_label(
    "Review Workflow"
)

review_status = st.radio(
    "Review Status",
    REVIEW_STATUSES,
    horizontal=True,
    key=status_key,
)


# ============================================================
# DETECT CHANGES
# ============================================================

original_values = {
    "ncaa_challenge_category":
        play.get("ncaa_challenge_category")
        or play.get("crs_category")
        or "",

    "play_category":
        play.get("play_category")
        or "",

    "play_category_other":
        play.get("play_category_other")
        or "",

    "is_starred":
        bool(
            play.get("is_starred")
        ),

    "crs_touch_context":
        play.get(
            "crs_touch_context"
        )
        or "",

    "crs_original_decision":
        play.get(
            "crs_original_decision"
        )
        or "",

    "crs_outcome":
        play.get("crs_outcome")
        or "",

    "crs_original_fault_changed":
        play.get(
            "crs_original_fault_changed"
        ),

    "challenge_length_seconds":
        play.get(
            "challenge_length_seconds"
        ),

    "is_unusable":
        bool(
            play.get(
                "is_unusable"
            )
        ),

    "unusable_reason":
        play.get(
            "unusable_reason"
        ),

    "unusable_notes":
        play.get(
            "unusable_notes"
        ),

    "review_decision_correct":
        play.get(
            "review_decision_correct"
        ),

    "use_for_training":
        bool(
            play.get(
                "use_for_training"
            )
        ),

    "involved_roles":
        involved_roles_list(
            play.get(
                "involved_roles"
            )
        ),

    "involved_people":
        play.get(
            "involved_people"
        )
        or "",

    "reviewer_notes":
        play.get("reviewer_notes")
        or "",

    "weekly_summary_note":
        play.get(
            "weekly_summary_note"
        )
        or "",

    "review_status":
        play.get("review_status")
        or "Not Viewed",
}


current_values = {
    "ncaa_challenge_category":
        category,

    "play_category":
        play_classification,

    "play_category_other":
        play_classification_other,

    "is_starred":
        is_starred,

    "crs_touch_context":
        touch_context,

    "crs_original_decision":
        original_decision,

    "crs_outcome":
        challenge_outcome,

    "crs_original_fault_changed":
        original_fault_changed,

    "challenge_length_seconds":
        current_length_seconds,

    "is_unusable":
        is_unusable,

    "unusable_reason":
        unusable_reason,

    "unusable_notes":
        unusable_notes,

    "review_decision_correct":
        review_decision_correct,

    "use_for_training":
        use_for_training,

    "involved_roles":
        involved_roles,

    "involved_people":
        involved_people,

    "reviewer_notes":
        reviewer_notes,

    "weekly_summary_note":
        weekly_summary_note,

    "review_status":
        review_status,
}


has_unsaved_changes = (
    original_values
    != current_values
)


save_message_key = (
    f"save_message_{play_id}"
)

if has_unsaved_changes:
    st.warning(
        (
            "● Unsaved changes — click Save Review "
            "before leaving this play."
        )
    )
else:
    saved_message = (
        st.session_state.get(
            save_message_key
        )
    )

    if saved_message:
        st.success(
            saved_message
        )
    else:
        st.success(
            "✓ All changes saved"
        )


# ============================================================
# SAVE + QUEUE NAVIGATION
# ============================================================

def save_current_review():
    if (
        is_challenge
        and play.get(
            "challenge_length_seconds"
        )
        is None
        and clean_text(
            st.session_state.get(
                length_key
            )
        )
        and current_length_seconds
        is None
    ):
        st.error(
            (
                "Length of Challenge must be entered "
                "as minutes:seconds, such as 1:24."
            )
        )
        return False

    update_data = {
        "ncaa_challenge_category":
            category,

        "play_category":
            play_classification,

        "play_category_other":
            (
                play_classification_other
                or None
            ),

        "is_starred":
            is_starred,

        "crs_touch_context":
            touch_context
            or None,

        "crs_original_decision":
            original_decision,

        "crs_outcome":
            challenge_outcome,

        "crs_original_fault_changed":
            original_fault_changed,

        "challenge_length_seconds":
            current_length_seconds,

        "is_unusable":
            is_unusable,

        "unusable_reason":
            unusable_reason,

        "unusable_notes":
            unusable_notes,

        "review_decision_correct":
            review_decision_correct,

        "use_for_training":
            use_for_training,

        "involved_roles":
            involved_roles,

        "involved_people":
            involved_people,

        "reviewer_notes":
            reviewer_notes,

        "weekly_summary_note":
            weekly_summary_note,

        "review_status":
            review_status,
    }

    try:
        (
            supabase
            .table("plays")
            .update(update_data)
            .eq(
                "id",
                play_id,
            )
            .execute()
        )

        save_time = (
            datetime.now()
            .strftime(
                "%I:%M:%S %p"
            )
        )

        st.session_state[
            save_message_key
        ] = (
            f"✓ Saved successfully "
            f"at {save_time}"
        )

        return True

    except Exception as exc:
        st.error(
            "The review could not be saved."
        )
        st.exception(exc)
        return False


def move_to_play(target_play_id):
    if target_play_id is None:
        return

    st.session_state[
        "editor_selected_play_id"
    ] = target_play_id

    st.session_state[
        "editor_play_picker"
    ] = target_play_id


nav1, save1, save2, nav2 = st.columns(
    [
        1.0,
        1.35,
        1.55,
        1.0,
    ]
)

with nav1:
    previous_clicked = st.button(
        "← Previous",
        use_container_width=True,
        disabled=(
            previous_play_id is None
            or has_unsaved_changes
        ),
        help=(
            "Save or discard current changes before moving."
            if has_unsaved_changes
            else None
        ),
    )

with save1:
    save_clicked = st.button(
        "Save Review",
        type="primary",
        use_container_width=True,
    )

with save2:
    save_next_clicked = st.button(
        "Save & Next →",
        type="primary",
        use_container_width=True,
        disabled=(
            next_play_id is None
        ),
        help=(
            "Save this review and immediately open the next play "
            "in the selected match."
        ),
    )

with nav2:
    next_clicked = st.button(
        "Next →",
        use_container_width=True,
        disabled=(
            next_play_id is None
            or has_unsaved_changes
        ),
        help=(
            "Save or discard current changes before moving."
            if has_unsaved_changes
            else None
        ),
    )


if previous_clicked:
    move_to_play(
        previous_play_id
    )
    st.rerun()


if next_clicked:
    move_to_play(
        next_play_id
    )
    st.rerun()


if save_clicked:
    if save_current_review():
        st.rerun()


if save_next_clicked:
    target_id = next_play_id

    if save_current_review():
        move_to_play(
            target_id
        )
        st.rerun()
