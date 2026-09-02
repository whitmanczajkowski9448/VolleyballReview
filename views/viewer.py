from datetime import date, timedelta

import json
import pandas as pd
import streamlit as st

from services.database import get_supabase
from services.dvsport_media import fresh_video_url
from services.video_player import render_keyboard_video_workspace
from services.auth import is_admin
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
from services.review_taxonomy import PLAY_CATEGORIES



# ============================================================
# HEADER
# ============================================================

render_page_header(
    "Play Library",
    (
        "Search, filter, and watch DV Sport challenge and POI media "
        "without changing review data."
    ),
    eyebrow="NCAA WVB • REVIEW LIBRARY",
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
            play.get("ncaa_challenge_category") or play.get("crs_category")
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
        "NCAA Challenge Category": (
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


def initialize(key, value):
    if key not in st.session_state:
        st.session_state[key] = value



def current_focus_play_id():
    value = st.session_state.get(
        "viewer_focus_play_id"
    )

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def clear_focus_mode():
    st.session_state.pop(
        "viewer_focus_play_id",
        None,
    )



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
    return (
        normalized_angle_name(
            angle.get("angle_name")
        )
        in {
            "REPLAY OUTPUT",
            "RO",
            "REPLAY",
        }
    )


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


df = pd.DataFrame(plays)


# ============================================================
# SIMPLE PLAY BROWSER
# ============================================================

render_section_label(
    "Choose a Play"
)

plays = df.to_dict("records")

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
            index=["All", "Challenge", "POI", "Fault"].index("All"),
            key="viewer_filter_play_type",
        )

    with f2:
        conference_filter = st.selectbox(
            "Conference",
            ["All"] + conferences,
            key="viewer_filter_conference",
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
            key="viewer_filter_status",
        )

    with f4:
        record_use_filter = st.selectbox(
            "Record Use",
            [
                "Usable Only",
                "All Records",
                "Unusable Only",
            ],
            key="viewer_filter_record_use",
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
            key="viewer_filter_date_mode",
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
                key="viewer_filter_start_date",
            )

        with d3:
            filter_end_date = st.date_input(
                "End Date",
                value=max_data_date,
                key="viewer_filter_end_date",
            )

        if filter_start_date > filter_end_date:
            st.error("Start Date cannot be after End Date.")
            st.stop()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        challenge_type_filter = st.selectbox(
            "DV Sport Challenge Type",
            ["All"] + challenge_types,
            key="viewer_filter_challenge_type",
        )

    with c2:
        crs_category_filter = st.selectbox(
            "NCAA Challenge Category",
            ["All"] + crs_categories,
            key="viewer_filter_crs_category",
        )

    with c3:
        outcome_filter = st.selectbox(
            "Challenge Outcome",
            ["All"] + outcomes,
            key="viewer_filter_outcome",
        )

    with c4:
        challenging_team_filter = st.selectbox(
            "Challenging Team",
            ["All"] + challenging_teams,
            key="viewer_filter_challenging_team",
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
            key="viewer_filter_accuracy",
        )

    with t2:
        training_filter = st.selectbox(
            "Training Use",
            [
                "All",
                "Marked for Training",
                "Not Marked",
            ],
            key="viewer_filter_training",
        )

    with t3:
        involved_filter = st.selectbox(
            "Who Was Involved",
            ["All"] + INVOLVED_ROLE_OPTIONS,
            key="viewer_filter_involved",
        )

    search_filter = st.text_input(
        "Search Match / Team / Score / Notes",
        placeholder=(
            "Type part of a match, team, score, category, or note..."
        ),
        key="viewer_filter_search",
    )

    if st.button(
        "Reset Filters",
        key="viewer_reset_filters",
    ):
        for state_key in list(st.session_state.keys()):
            if state_key.startswith("viewer_filter_"):
                st.session_state.pop(state_key, None)

        st.session_state.pop("viewer_match_picker", None)
        st.session_state.pop("viewer_play_picker", None)
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
                clean_text(item.get("ncaa_challenge_category") or item.get("crs_category")),
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
    category_text = clean_text(item.get("ncaa_challenge_category") or item.get("crs_category"))
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


match_picker_key = "viewer_match_picker"
play_picker_key = "viewer_play_picker"

if st.session_state.get(match_picker_key) not in match_keys:
    current_id = st.session_state.get("viewer_selected_play_id")
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

st.session_state["viewer_selected_play_id"] = selected_play_id
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

        if play.get("is_starred"):
            st.markdown("### ★ STARRED PLAY")
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
            clean_text(play.get("ncaa_challenge_category") or play.get("crs_category")),
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
# SIMPLE MATCH NAVIGATION
# ============================================================

nav_left, nav_center, nav_right = st.columns([1.0, 2.2, 1.0])

with nav_left:
    if st.button(
        "← Previous",
        use_container_width=True,
        disabled=(previous_play_id is None),
        key="viewer_previous_simple",
    ):
        st.session_state["viewer_play_picker"] = previous_play_id
        st.session_state["viewer_selected_play_id"] = previous_play_id
        st.rerun()

with nav_center:
    st.markdown(
        f"<div style='text-align:center; padding-top:0.55rem;'>"
        f"Play <strong>{selected_index + 1}</strong> of "
        f"<strong>{len(queue_ids)}</strong> in this match"
        f"</div>",
        unsafe_allow_html=True,
    )

with nav_right:
    if st.button(
        "Next →",
        use_container_width=True,
        disabled=(next_play_id is None),
        key="viewer_next_simple",
    ):
        st.session_state["viewer_play_picker"] = next_play_id
        st.session_state["viewer_selected_play_id"] = next_play_id
        st.rerun()


# ============================================================
# RECORD USE NOTICE
# ============================================================

if bool(
    play.get(
        "is_unusable"
    )
):
    reason = clean_text(
        play.get(
            "unusable_reason"
        )
    )

    detail = clean_text(
        play.get(
            "unusable_notes"
        )
    )

    message = (
        "UNUSABLE — This record is excluded from all "
        "dashboard analysis and coordinator reports."
    )

    if reason:
        message += f" Reason: {reason}."

    if detail:
        message += f" {detail}"

    st.warning(
        message,
        icon="⚠️",
    )


# ============================================================
# TOP CHALLENGE DOWNLOAD
# ============================================================

top_video_angles = video_angles_from_play(play)


if normalized_play_type(
    play.get("play_type")
) == "Challenge":
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
            "viewer",
        )

    with action_email:
        if is_admin():
            render_email_challenge_button(
                play,
                top_video_angles,
                supabase,
                "viewer",
            )


# ============================================================
# SUMMARY
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


i1, i2, i3, i4 = st.columns(
    4
)

with i1:
    st.caption("Conference")
    st.write(
        clean_value(
            play.get("conference")
        )
    )

with i2:
    st.caption("Date")
    st.write(
        clean_value(
            play.get("match_date")
        )
    )

with i3:
    st.caption("Set")
    st.write(
        clean_value(
            play.get("set_number")
        )
    )

with i4:
    st.caption("Score")
    st.write(
        clean_value(
            play.get("score")
        )
    )


# ============================================================
# PLAY-SPECIFIC VIDEO
# ============================================================

render_section_label(
    "Play Video"
)

angles = video_angles_from_play(play)

# Remove missing/blank URLs before handing the angle collection to the
# keyboard-aware workspace. The database remains challenge/play-centric:
# every angle still comes directly from this play's video_urls field.
angles = [
    angle
    for angle in angles
    if video_url_is_playable(
        clean_text(
            angle.get("video_url")
        )
    )
]

angles.sort(
    key=video_sort_key
)

if not angles:
    render_empty(
        "DV Sport does not have a video URL attached to this play."
    )

else:
    st.caption(
        "Click a video to make it the active shortcut angle. "
        "Keyboard controls only act on the highlighted ACTIVE player."
    )

    render_keyboard_video_workspace(
        angles,
        key=f"viewer_play_{play.get('id', 'unknown')}",
    )


# ============================================================
# REVIEW TAGS
# ============================================================

if normalized_play_type(
    play.get("play_type")
) == "Challenge":
    render_section_label(
        "Review Tags"
    )

    tag1, tag2, tag3 = st.columns(3)

    with tag1:
        st.caption(
            "Review Decision"
        )

        accuracy_value = play.get(
            "review_decision_correct"
        )

        if accuracy_value is True:
            st.success("✓ Correct")
        elif accuracy_value is False:
            st.error("✕ Incorrect")
        else:
            st.info("Not Tagged")

    with tag2:
        st.caption(
            "Use in Training"
        )

        if play.get(
            "use_for_training"
        ) is True:
            st.success(
                "✓ Marked for Training"
            )
        else:
            st.write("Not Marked")

    with tag3:
        st.caption(
            "Who Was Involved"
        )
        st.write(
            involved_roles_label(
                play.get(
                    "involved_roles"
                )
            )
        )

    if clean_text(
        play.get(
            "involved_people"
        )
    ):
        st.caption(
            "Names / Details"
        )
        st.write(
            play.get(
                "involved_people"
            )
        )


# ============================================================
# REVIEW RECORD
# ============================================================

render_section_label(
    "Review Record"
)

r1, r2 = st.columns(2)

with r1:
    st.caption(
        "NCAA Challenge Category"
    )
    st.write(
        clean_value(
            play.get("ncaa_challenge_category") or play.get("crs_category")
        )
    )

    st.caption(
        "Original Fault Decision"
    )
    st.write(
        clean_value(
            play.get(
                "crs_original_decision"
            )
        )
    )

    if clean_text(
        play.get("crs_touch_context")
    ):
        st.caption(
            "Touch Context"
        )
        st.write(
            play.get(
                "crs_touch_context"
            )
        )


with r2:
    st.caption(
        "Challenge Outcome"
    )
    st.write(
        clean_value(
            play.get("crs_outcome")
            or play.get(
                "challenge_result"
            )
        )
    )

    st.caption(
        "Challenging Team"
    )
    st.write(
        clean_value(
            play.get(
                "challenging_team"
            )
        )
    )

    length_seconds = (
        play.get(
            "challenge_length_seconds"
        )
    )

    st.caption(
        "Length of Challenge"
    )

    if length_seconds is not None:
        try:
            total = int(
                length_seconds
            )

            st.write(
                (
                    f"{total // 60}:"
                    f"{total % 60:02d}"
                )
            )

        except Exception:
            st.write("—")

    else:
        st.write("—")


if clean_text(
    play.get("reviewer_notes")
):
    st.caption(
        "Reviewer Notes"
    )
    st.write(
        play.get(
            "reviewer_notes"
        )
    )


if clean_text(
    play.get("weekly_summary_note")
):
    st.caption(
        "Weekly Summary Note"
    )
    st.info(
        play.get(
            "weekly_summary_note"
        )
    )
