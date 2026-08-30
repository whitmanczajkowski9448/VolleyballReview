from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

from services.database import get_supabase
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
        "Review": (
            f"?review_play_id={play.get('id')}"
        ),
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


def initialize(key, value):
    if key not in st.session_state:
        st.session_state[key] = value



def current_focus_play_id():
    value = st.query_params.get(
        "review_play_id"
    )

    if isinstance(value, list):
        value = (
            value[0]
            if value
            else None
        )

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def clear_focus_mode():
    if (
        "review_play_id"
        in st.query_params
    ):
        del st.query_params[
            "review_play_id"
        ]



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


def render_video_player(
    angle,
    primary=False,
):
    """
    Render nothing at all when this angle has no usable URL.
    """
    url = clean_text(
        angle.get("video_url")
    )

    if not has_usable_video_url(url):
        return

    name = (
        clean_text(
            angle.get("angle_name")
        )
        or "Video"
    )

    if primary:
        st.subheader(name)
    else:
        st.markdown(
            f"**{name}**"
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


df = pd.DataFrame(plays)


# ============================================================
# FILTERABLE VIEW QUEUE
# ============================================================

render_section_label(
    "Find a Play"
)

# Normalize once for filtering.
plays = df.to_dict(
    "records"
)

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
                "All",
                "Challenge",
                "POI",
            ],
            index=0,
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
        date_filter = st.selectbox(
            "Date Range",
            [
                "All Dates",
                "Last 7 Days",
                "Custom",
            ],
            key="viewer_filter_date_mode",
        )


    record_use_filter = st.selectbox(
        "Record Use",
        [
            "Usable Only",
            "All Records",
            "Unusable Only",
        ],
        index=0,
        key="viewer_filter_record_use",
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
                key="viewer_filter_start_date",
            )

        with d2:
            filter_end_date = st.date_input(
                "End Date",
                value=max_data_date,
                key="viewer_filter_end_date",
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
    # CHALLENGE-SPECIFIC FILTERS
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
                key="viewer_filter_challenge_type",
            )

        with c2:
            crs_category_filter = st.selectbox(
                "CRS Category",
                ["All"] + crs_categories,
                key="viewer_filter_crs_category",
            )

        with c3:
            outcome_filter = st.selectbox(
                "Challenge Outcome",
                ["All"] + outcomes,
                key="viewer_filter_outcome",
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
                key="viewer_filter_challenging_team",
            )

        with c5:
            search_filter = st.text_input(
                "Search Match / Team / Score",
                placeholder=(
                    "Example: Wisconsin, Penn State, 23-22..."
                ),
                key="viewer_filter_search",
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
                key="viewer_filter_accuracy",
            )

        with tag2:
            training_filter = st.selectbox(
                "Training Use",
                [
                    "All",
                    "Marked for Training",
                    "Not Marked",
                ],
                key="viewer_filter_training",
            )

        with tag3:
            involved_filter = st.selectbox(
                "Who Was Involved",
                ["All"] + INVOLVED_ROLE_OPTIONS,
                key="viewer_filter_involved",
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
            placeholder="Search the POI library...",
            key="viewer_filter_search_poi",
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
                clean_text(
                    play.get("reviewer_notes")
                ),
                clean_text(
                    play.get("weekly_summary_note")
                ),
            ]
        ).lower()

        if needle not in haystack:
            continue

    filtered_plays.append(play)


# Viewer defaults to newest first.
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
    ),
    reverse=True,
)


if not filtered_plays:
    render_empty(
        "No plays match those filters."
    )
    st.stop()


# ============================================================
# CLICKABLE TABLE
# ============================================================

with st.expander(
    "Review Queue",
    expanded=(not focus_mode),
):
    st.caption(
        (
            f"{len(filtered_plays):,} play(s) match the current filters. "
            "Click a row or use the Review link to open it."
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
        "viewer_queue_reset",
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
            "viewer_review_queue_"
            f"{st.session_state['viewer_queue_reset']}"
        ),
        column_config={
            "Review": st.column_config.LinkColumn(
                "Review",
                display_text="Review",
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
            st.session_state[
                "viewer_selected_play_id"
            ] = filtered_plays[
                clicked_index
            ]["id"]


# Review hyperlinks must open the exact play requested, even when
# that play would not be the first item in the current filtered queue.
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
        "viewer_selected_play_id"
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
        "viewer_selected_play_id"
    )

    if selected_play_id not in queue_ids:
        selected_play_id = queue_ids[0]

        st.session_state[
            "viewer_selected_play_id"
        ] = selected_play_id

    selected_index = queue_ids.index(
        selected_play_id
    )

    play = filtered_plays[
        selected_index
    ]

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


def move_to_play(target_play_id):
    if target_play_id is None:
        return

    st.session_state[
        "viewer_selected_play_id"
    ] = target_play_id

    st.session_state[
        "viewer_queue_reset"
    ] += 1


nav_left, queue_position, nav_right = st.columns(
    [
        1.0,
        2.5,
        1.0,
    ]
)

with nav_left:
    previous_clicked = st.button(
        "← Previous",
        use_container_width=True,
        disabled=(
            previous_play_id is None
        ),
        key="viewer_previous",
    )

with queue_position:
    st.markdown(
        (
            f"<div style='text-align:center; padding-top:0.55rem;'>"
            f"Viewing <strong>{selected_index + 1:,}</strong> "
            f"of <strong>{len(queue_ids):,}</strong> "
            f"in the filtered set"
            f"</div>"
        ),
        unsafe_allow_html=True,
    )

with nav_right:
    next_clicked = st.button(
        "Next →",
        use_container_width=True,
        disabled=(
            next_play_id is None
        ),
        key="viewer_next",
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
            key="viewer_back_to_queue",
        ):
            clear_focus_mode()
            st.session_state[
                "viewer_queue_reset"
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

try:
    top_video_response = (
        supabase
        .table("video_angles")
        .select("*")
        .eq(
            "play_id",
            play["id"],
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

try:
    video_response = (
        supabase
        .table("video_angles")
        .select("*")
        .eq(
            "play_id",
            play["id"],
        )
        .order("id")
        .execute()
    )

    angles = (
        video_response.data
        or []
    )

except Exception:
    angles = []


# CRITICAL:
# Remove rows with no real URL BEFORE doing any layout work.
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
        "DV Sport does not have usable video attached to this play."
    )

else:
    pgm = next(
        (
            angle
            for angle in angles
            if is_pgm(angle)
        ),
        None,
    )

    replay_output = next(
        (
            angle
            for angle in angles
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
        left, right = st.columns(2)

        with left:
            render_video_player(
                primary_angles[0],
                primary=True,
            )

        with right:
            render_video_player(
                primary_angles[1],
                primary=True,
            )

    elif len(primary_angles) == 1:
        render_video_player(
            primary_angles[0],
            primary=True,
        )


    secondary = [
        angle
        for angle in angles
        if angle.get("id")
        not in primary_ids
    ]


    if secondary:
        st.caption(
            "ADDITIONAL ANGLES"
        )

        for start in range(
            0,
            len(secondary),
            3,
        ):
            row = secondary[
                start:
                start + 3
            ]

            columns = st.columns(
                len(row)
            )

            for column, angle in zip(
                columns,
                row,
            ):
                with column:
                    render_video_player(
                        angle,
                        primary=False,
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
        "CRS Category"
    )
    st.write(
        clean_value(
            play.get("crs_category")
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
