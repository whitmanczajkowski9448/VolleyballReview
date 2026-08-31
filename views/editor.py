import pandas as pd
import requests
import streamlit as st
from datetime import date, datetime, timedelta

from services.database import get_supabase
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


def has_usable_video_url(value):
    """
    Basic string-level URL screening.
    """
    url = clean_text(value)

    if not url:
        return False

    lowered = url.lower()

    if lowered in {
        "none",
        "null",
        "nan",
        "<na>",
    }:
        return False

    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
    )


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def video_url_is_playable(url):
    """
    Verify that a URL actually responds like usable media.
    """
    if not has_usable_video_url(url):
        return False

    try:
        response = requests.get(
            url,
            headers={
                "Range": "bytes=0-1",
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64)"
                ),
            },
            stream=True,
            timeout=8,
            allow_redirects=True,
        )

        try:
            if response.status_code not in {
                200,
                206,
            }:
                return False

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    "",
                )
                .split(";")[0]
                .strip()
                .lower()
            )

            if (
                content_type.startswith("text/")
                or "html" in content_type
                or content_type.startswith("image/")
                or "json" in content_type
                or "xml" in content_type
            ):
                return False

            if (
                content_type.startswith("video/")
                or content_type
                in {
                    "application/octet-stream",
                    "application/mp4",
                    "binary/octet-stream",
                    "application/vnd.apple.mpegurl",
                    "application/x-mpegurl",
                }
            ):
                return True

            path_only = (
                url.split("?")[0]
                .lower()
            )

            return path_only.endswith(
                (
                    ".mp4",
                    ".m4v",
                    ".mov",
                    ".webm",
                    ".m3u8",
                )
            )

        finally:
            response.close()

    except requests.RequestException:
        return False


def play_label(play):
    return (
        f"{clean_value(play.get('conference'), '')} | "
        f"{clean_value(play.get('match_name'), '')} | "
        f"{clean_value(play.get('play_type'), 'Play')} | "
        f"Set {clean_value(play.get('set_number'), '—')} | "
        f"{clean_value(play.get('score'), '—')}"
    )


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
    if key not in st.session_state:
        st.session_state[
            key
        ] = value



def current_focus_play_id():
    value = st.session_state.get(
        "editor_focus_play_id"
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
        "editor_focus_play_id",
        None,
    )



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


def render_video_player(
    angle,
    primary=False,
):
    """
    Render absolutely nothing for an angle with no real URL.
    """
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
        st.subheader(
            angle_name
        )
    else:
        st.markdown(
            f"**{angle_name}**"
        )

    st.video(url)

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
# REVIEW QUEUE + FILTERS
# ============================================================

render_section_label(
    "Review Queue"
)

# Normalize once for filtering.
for play in plays:
    play["_queue_play_type"] = (
        normalized_play_type(
            play.get("play_type")
        )
    )
    play["_queue_unusable"] = bool(
        play.get(
            "is_unusable"
        )
    )
    play["_queue_status"] = (
        normalized_review_status(
            play.get("review_status")
        )
    )
    play["_queue_outcome"] = (
        normalize_outcome(play)
    )
    play["_queue_category"] = (
        challenge_category_for_queue(
            play
        )
    )
    play["_queue_accuracy"] = (
        decision_accuracy_label(
            play.get(
                "review_decision_correct"
            )
        )
    )
    play["_queue_training"] = (
        training_label(
            play.get(
                "use_for_training"
            )
        )
    )
    play["_queue_involved_roles"] = (
        involved_roles_list(
            play.get(
                "involved_roles"
            )
        )
    )
    play["_queue_date"] = date_value(
        play.get("match_date")
    )


conferences = sorted(
    {
        clean_text(
            play.get("conference")
        )
        for play in plays
        if clean_text(
            play.get("conference")
        )
    }
)

challenge_types = sorted(
    {
        clean_text(
            play.get("challenge_type")
        )
        for play in plays
        if (
            play["_queue_play_type"]
            == "Challenge"
            and clean_text(
                play.get("challenge_type")
            )
        )
    }
)

crs_categories = sorted(
    {
        play["_queue_category"]
        for play in plays
        if (
            play["_queue_play_type"]
            == "Challenge"
        )
    }
)

outcomes = sorted(
    {
        play["_queue_outcome"]
        for play in plays
        if (
            play["_queue_play_type"]
            == "Challenge"
        )
    }
)

challenging_teams = sorted(
    {
        clean_text(
            play.get("challenging_team")
        )
        for play in plays
        if (
            play["_queue_play_type"]
            == "Challenge"
            and clean_text(
                play.get("challenging_team")
            )
        )
    }
)

INVOLVED_ROLE_OPTIONS = ['R1', 'R2', 'Line Judge', 'Coach', 'Player', 'Scorer / Table', 'Review Official / Technician', 'Other']

valid_dates = [
    play["_queue_date"]
    for play in plays
    if play["_queue_date"]
    is not None
]

min_data_date = (
    min(valid_dates)
    if valid_dates
    else date.today()
)

max_data_date = (
    max(valid_dates)
    if valid_dates
    else date.today()
)


focus_play_id = current_focus_play_id()
focus_mode = focus_play_id is not None

with st.expander(
    "Filters",
    expanded=(not focus_mode),
):
    # ----------------------------
    # FILTER ROW 1
    # ----------------------------

    f1, f2, f3, f4 = st.columns(
        [
            1.0,
            1.0,
            1.1,
            1.15,
        ]
    )

    with f1:
        play_type_filter = st.selectbox(
            "Play Type",
            [
                "Challenge",
                "POI",
                "All",
            ],
            index=0,
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
        date_filter = st.selectbox(
            "Date Range",
            [
                "All Dates",
                "Last 7 Days",
                "Custom",
            ],
            key="editor_filter_date_mode",
        )


    record_use_filter = st.selectbox(
        "Record Use",
        [
            "Usable Only",
            "All Records",
            "Unusable Only",
        ],
        index=0,
        key="editor_filter_record_use",
        help=(
            "Unusable records stay available here, but are excluded "
            "from dashboards and coordinator reports."
        ),
    )


    # ----------------------------
    # DATE RANGE
    # ----------------------------

    filter_start_date = None
    filter_end_date = None

    if date_filter == "Last 7 Days":
        filter_end_date = date.today()
        filter_start_date = (
            filter_end_date
            - timedelta(days=7)
        )

    elif date_filter == "Custom":
        d1, d2 = st.columns(2)

        with d1:
            filter_start_date = st.date_input(
                "Start Date",
                value=min_data_date,
                key="editor_filter_start_date",
            )

        with d2:
            filter_end_date = st.date_input(
                "End Date",
                value=max_data_date,
                key="editor_filter_end_date",
            )

        if (
            filter_start_date
            > filter_end_date
        ):
            st.error(
                "Start Date cannot be after End Date."
            )
            st.stop()


    # ----------------------------
    # CHALLENGE FILTERS
    # ----------------------------

    challenge_filters_active = (
        play_type_filter
        in {
            "Challenge",
            "All",
        }
    )

    if challenge_filters_active:
        c1, c2, c3 = st.columns(3)

        with c1:
            challenge_type_filter = st.selectbox(
                "DV Sport Challenge Type",
                ["All"] + challenge_types,
                key="editor_filter_challenge_type",
            )

        with c2:
            crs_category_filter = st.selectbox(
                "CRS Category",
                ["All"] + crs_categories,
                key="editor_filter_crs_category",
            )

        with c3:
            outcome_filter = st.selectbox(
                "Challenge Outcome",
                ["All"] + outcomes,
                key="editor_filter_outcome",
            )

        c4, c5 = st.columns(
            [
                1.0,
                2.0,
            ]
        )

        with c4:
            challenging_team_filter = st.selectbox(
                "Challenging Team",
                ["All"] + challenging_teams,
                key="editor_filter_challenging_team",
            )

        with c5:
            search_filter = st.text_input(
                "Search Match / Team / Score",
                placeholder=(
                    "Example: Wisconsin, Penn State, 23-22..."
                ),
                key="editor_filter_search",
            )

        tag1, tag2, tag3 = st.columns(3)

        with tag1:
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

        with tag2:
            training_filter = st.selectbox(
                "Training Use",
                [
                    "All",
                    "Marked for Training",
                    "Not Marked",
                ],
                key="editor_filter_training",
            )

        with tag3:
            involved_filter = st.selectbox(
                "Who Was Involved",
                ["All"] + INVOLVED_ROLE_OPTIONS,
                key="editor_filter_involved",
            )

    else:
        challenge_type_filter = "All"
        crs_category_filter = "All"
        outcome_filter = "All"
        challenging_team_filter = "All"
        accuracy_filter = "All"
        training_filter = "All"
        involved_filter = "All"

        search_filter = st.text_input(
            "Search Match / Team / Score",
            placeholder="Search the POI queue...",
            key="editor_filter_search_poi",
        )



# ============================================================
# APPLY FILTERS
# ============================================================

filtered_plays = []

for play in plays:
    if (
        record_use_filter == "Usable Only"
        and play["_queue_unusable"]
    ):
        continue

    if (
        record_use_filter == "Unusable Only"
        and not play["_queue_unusable"]
    ):
        continue

    if (
        play_type_filter != "All"
        and play["_queue_play_type"]
        != play_type_filter
    ):
        continue

    if (
        conference_filter != "All"
        and clean_text(
            play.get("conference")
        )
        != conference_filter
    ):
        continue

    if (
        status_filter != "All"
        and play["_queue_status"]
        != status_filter
    ):
        continue

    if (
        filter_start_date
        is not None
        and (
            play["_queue_date"]
            is None
            or play["_queue_date"]
            < filter_start_date
        )
    ):
        continue

    if (
        filter_end_date
        is not None
        and (
            play["_queue_date"]
            is None
            or play["_queue_date"]
            > filter_end_date
        )
    ):
        continue

    if (
        play["_queue_play_type"]
        == "Challenge"
    ):
        if (
            challenge_type_filter
            != "All"
            and clean_text(
                play.get("challenge_type")
            )
            != challenge_type_filter
        ):
            continue

        if (
            crs_category_filter
            != "All"
            and play["_queue_category"]
            != crs_category_filter
        ):
            continue

        if (
            outcome_filter
            != "All"
            and play["_queue_outcome"]
            != outcome_filter
        ):
            continue

        if (
            challenging_team_filter
            != "All"
            and clean_text(
                play.get("challenging_team")
            )
            != challenging_team_filter
        ):
            continue

        if (
            accuracy_filter != "All"
            and play["_queue_accuracy"]
            != accuracy_filter
        ):
            continue

        if (
            training_filter == "Marked for Training"
            and play["_queue_training"] != "Yes"
        ):
            continue

        if (
            training_filter == "Not Marked"
            and play["_queue_training"] != "No"
        ):
            continue

        if (
            involved_filter != "All"
            and involved_filter
            not in play[
                "_queue_involved_roles"
            ]
        ):
            continue

    needle = clean_text(
        search_filter
    ).lower()

    if needle:
        haystack = " | ".join(
            [
                clean_text(
                    play.get("match_name")
                ),
                clean_text(
                    play.get("challenging_team")
                ),
                clean_text(
                    play.get("score")
                ),
                clean_text(
                    play.get("challenge_type")
                ),
                clean_text(
                    play.get("crs_category")
                ),
                decision_accuracy_label(
                    play.get(
                        "review_decision_correct"
                    )
                ),
                involved_roles_label(
                    play.get(
                        "involved_roles"
                    )
                ),
                clean_text(
                    play.get(
                        "involved_people"
                    )
                ),
                clean_text(
                    play.get(
                        "unusable_reason"
                    )
                ),
                clean_text(
                    play.get(
                        "unusable_notes"
                    )
                ),
            ]
        ).lower()

        if needle not in haystack:
            continue

    filtered_plays.append(play)


# Stable review order: oldest-to-newest inside the selected queue,
# then match/set/score. This makes Save & Next predictable.
filtered_plays.sort(
    key=lambda play: (
        play["_queue_date"]
        or date.min,
        clean_text(
            play.get("conference")
        ),
        clean_text(
            play.get("match_name")
        ),
        int(
            play.get("set_number")
            or 0
        ),
        clean_text(
            play.get("score")
        ),
        int(
            play.get("id")
            or 0
        ),
    )
)


if not filtered_plays:
    render_empty(
        "No plays match those filters."
    )
    st.stop()


# ============================================================
# CLICKABLE REVIEW QUEUE TABLE
# ============================================================

with st.expander(
    "Review Queue",
    expanded=(not focus_mode),
):
    st.caption(
        (
            f"{len(filtered_plays):,} play(s) in the current queue. "
            "Click any row to review that exact play."
        )
    )

    queue_df = pd.DataFrame(
        [
            queue_row(
                play,
                index + 1,
            )
            for index, play
            in enumerate(filtered_plays)
        ]
    )

    initialize(
        "editor_queue_reset",
        0,
    )

    queue_event = st.dataframe(
        queue_df,
        use_container_width=True,
        hide_index=True,
        height=min(
            460,
            42 + 35 * len(queue_df),
        ),
        on_select="rerun",
        selection_mode="single-row",
        key=(
            "editor_review_queue_"
            f"{st.session_state['editor_queue_reset']}"
        ),
        column_config={
            "Review": st.column_config.TextColumn(
                "Review",
                width="small",
            ),
            "#": st.column_config.NumberColumn(
                "#",
                width="small",
            ),
            "Status": st.column_config.TextColumn(
                "Status",
                width="medium",
            ),
            "Use": st.column_config.TextColumn(
                "Use",
                width="small",
            ),
            "Date": st.column_config.TextColumn(
                "Date",
                width="small",
            ),
            "Conference": st.column_config.TextColumn(
                "Conference",
                width="small",
            ),
            "Match": st.column_config.TextColumn(
                "Match",
                width="large",
            ),
            "Type": st.column_config.TextColumn(
                "Type",
                width="small",
            ),
            "Set": st.column_config.TextColumn(
                "Set",
                width="small",
            ),
            "Score": st.column_config.TextColumn(
                "Score",
                width="small",
            ),
            "Challenging Team": st.column_config.TextColumn(
                "Challenging Team",
                width="medium",
            ),
            "Challenge Type": st.column_config.TextColumn(
                "Challenge Type",
                width="medium",
            ),
            "CRS Category": st.column_config.TextColumn(
                "CRS Category",
                width="medium",
            ),
            "Outcome": st.column_config.TextColumn(
                "Outcome",
                width="medium",
            ),
            "Decision Correct?": st.column_config.TextColumn(
                "Decision Correct?",
                width="medium",
            ),
            "Training": st.column_config.TextColumn(
                "Training",
                width="small",
            ),
            "Involved": st.column_config.TextColumn(
                "Involved",
                width="large",
            ),
        },
    )

    selected_rows = []

    try:
        selected_rows = (
            queue_event.selection.rows
        )
    except Exception:
        selected_rows = []

    if selected_rows:
        clicked_index = selected_rows[0]

        if (
            0 <= clicked_index
            < len(filtered_plays)
        ):
            clicked_id = filtered_plays[
                clicked_index
            ]["id"]

            selected_changed = (
                st.session_state.get(
                    "editor_selected_play_id"
                )
                != clicked_id
            )

            focus_changed = (
                st.session_state.get(
                    "editor_focus_play_id"
                )
                != clicked_id
            )

            st.session_state[
                "editor_selected_play_id"
            ] = clicked_id

            st.session_state[
                "editor_focus_play_id"
            ] = clicked_id

            if (
                selected_changed
                or focus_changed
            ):
                st.rerun()


# Focused review opens the exact play selected in the queue.
focus_play = None

if focus_play_id is not None:
    for candidate in plays:
        try:
            candidate_id = int(
                candidate.get("id")
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if candidate_id == focus_play_id:
            focus_play = candidate
            break


if focus_play is not None:
    # Focus mode bypasses the filtered queue for the selected record.
    # The filtered queue still exists in the collapsed expander, but
    # it cannot override the hyperlink target.
    play = focus_play
    selected_play_id = focus_play_id

    st.session_state[
        "editor_selected_play_id"
    ] = selected_play_id

    queue_ids = [
        item["id"]
        for item in filtered_plays
    ]

    if selected_play_id in queue_ids:
        selected_index = queue_ids.index(
            selected_play_id
        )
    else:
        # The focused challenge may fall outside the active filters.
        # Treat it as a one-item focused queue for navigation purposes.
        queue_ids = [
            selected_play_id
        ]
        selected_index = 0

else:
    queue_ids = [
        item["id"]
        for item in filtered_plays
    ]

    selected_play_id = st.session_state.get(
        "editor_selected_play_id"
    )

    if selected_play_id not in queue_ids:
        selected_play_id = queue_ids[0]

        st.session_state[
            "editor_selected_play_id"
        ] = selected_play_id

    selected_index = queue_ids.index(
        selected_play_id
    )

    play = filtered_plays[
        selected_index
    ]

play_id = play["id"]

is_challenge = (
    play["_queue_play_type"]
    == "Challenge"
)

previous_play_id = (
    queue_ids[
        selected_index - 1
    ]
    if selected_index > 0
    else None
)

next_play_id = (
    queue_ids[
        selected_index + 1
    ]
    if selected_index
    < len(queue_ids) - 1
    else None
)

st.caption(
    (
        f"Reviewing {selected_index + 1:,} of "
        f"{len(queue_ids):,} in the filtered queue."
    )
)


# ============================================================
# FOCUSED REVIEW MODE
# ============================================================

if focus_mode:
    focus_left, focus_right = st.columns(
        [
            1.15,
            3.85,
        ]
    )

    with focus_left:
        if st.button(
            "← Back to Queue",
            use_container_width=True,
            key="editor_back_to_queue",
        ):
            clear_focus_mode()
            st.session_state[
                "editor_queue_reset"
            ] += 1
            st.rerun()

    with focus_right:
        st.info(
            (
                "Focused review mode — Filters and Review Queue "
                "are collapsed so you can concentrate on this play."
            )
        )


# ============================================================
# TOP CHALLENGE DOWNLOAD
# ============================================================

try:
    top_video_response = (
        supabase
        .table("video_angles")
        .select("*")
        .eq(
            "play_id",
            play_id,
        )
        .order("id")
        .execute()
    )

    top_video_angles = (
        top_video_response.data
        or []
    )

except Exception:
    top_video_angles = []


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

try:
    video_response = (
        supabase
        .table("video_angles")
        .select("*")
        .eq(
            "play_id",
            play_id,
        )
        .order("id")
        .execute()
    )

    video_angles = (
        video_response.data
        or []
    )

except Exception:
    video_angles = []


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
        "DV Sport does not have usable video attached to this play."
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
# CHALLENGE CRS OPTIONS
# ============================================================

CRS_CATEGORIES = [
    "",
    "Ball ruled in or out",
    "Ball contacting a player",
    "Net fault by player",
    "Attack line fault",
    "Service foot fault",
    "Center line fault",
]

TOUCH_CONTEXTS = [
    "",
    "IN/OUT",
    "BRA/BRB/RO",
    "2 or 4 HITS",
]

ORIGINAL_DECISIONS = {
    "Ball ruled in or out": [
        "",
        "Ball in",
        "Ball out",
        "Successful pancake",
        "Unsuccessful pancake",
    ],

    "Ball contacting a player": [
        "",
        "Touch",
        "No touch",
    ],

    "Net fault by player": [
        "",
        "Net fault",
        "No net fault",
    ],

    "Attack line fault": [
        "",
        "Back-row attack",
        "Not a back-row attack",
        "Libero in the front zone",
        "Libero not in the front zone",
    ],

    "Service foot fault": [
        "",
        "Foot fault",
        "No foot fault",
    ],

    "Center line fault": [
        "",
        "CL fault",
        "No CL fault",
    ],

    "": [""],
}

CRS_OUTCOMES = [
    "",
    "Original outcome confirmed",
    "Original outcome reversed",
    "Original outcome stands",
    "Mechanical or video failure",
]

REVIEW_STATUSES = [
    "Not Viewed",
    "Needs Review",
    "Complete",
]


# ============================================================
# SESSION STATE
# ============================================================

category_key = (
    f"category_{play_id}"
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
    play.get("crs_category")
    or "",
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
        "CRS Classification"
    )

    category = st.selectbox(
        "Challenge Category",
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
    # POIs do not use challenge-only CRS fields.
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
    "crs_category":
        play.get("crs_category")
        or "",

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
    "crs_category":
        category,

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
        "crs_category":
            category,

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

    # Reset the dataframe-selection widget so an old clicked row
    # cannot override the programmatic Previous/Next selection.
    st.session_state[
        "editor_queue_reset"
    ] += 1


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
            "in the filtered queue."
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
