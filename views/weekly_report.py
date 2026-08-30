from datetime import date, timedelta

import pandas as pd
import streamlit as st

from services.database import get_supabase
from services.auth import require_admin
from services.ui import (
    render_empty,
    render_kpi,
    render_page_header,
    render_section_label,
)


# ============================================================
# PAGE
# ============================================================

require_admin()

render_page_header(
    "Weekly Coordinator Report",
    (
        "Review coordinator-ready challenge metrics, completion status, "
        "and special notes for a selected week or custom date range."
    ),
    eyebrow="NCAA WVB • COORDINATOR REPORTING",
)

supabase = get_supabase()


# ============================================================
# HELPERS
# ============================================================

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


def normalize_outcome(row):
    crs_outcome = clean_text(
        row.get("crs_outcome")
    )

    source_outcome = clean_text(
        row.get("challenge_result")
    )

    raw = (
        crs_outcome
        if crs_outcome
        else source_outcome
    )

    if not raw:
        return "Not Tagged"

    upper = raw.upper()

    if "REVER" in upper:
        return "REVERSED"

    if "CONFIRM" in upper:
        return "CONFIRMED"

    if (
        "STAND" in upper
        or "INCONCLUSIVE" in upper
    ):
        return "STANDS"

    if (
        "MECHANICAL" in upper
        or "VIDEO FAILURE" in upper
        or "VIDEO FAIL" in upper
    ):
        return "MECHANICAL / VIDEO FAILURE"

    return upper


def monday_for(day):
    return day - timedelta(
        days=day.weekday()
    )


def sunday_for(monday):
    return monday + timedelta(
        days=6
    )


def week_label(monday):
    sunday = sunday_for(monday)

    return (
        f"{monday:%b %d, %Y} – "
        f"{sunday:%b %d, %Y}"
    )


def format_seconds(value):
    if value is None:
        return "—"

    try:
        if pd.isna(value):
            return "—"
    except Exception:
        pass

    try:
        seconds = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return "—"

    return (
        f"{seconds // 60}:"
        f"{seconds % 60:02d}"
    )


def date_range_caption(
    start_date,
    end_date,
):
    day_count = (
        end_date
        - start_date
    ).days + 1

    return (
        f"{start_date:%B %d, %Y} through "
        f"{end_date:%B %d, %Y} "
        f"({day_count:,} day"
        f"{'' if day_count == 1 else 's'})"
    )


# ============================================================
# LOAD DATA
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

    rows = response.data or []

except Exception as exc:
    st.error(
        "Could not load coordinator report data."
    )
    st.exception(exc)
    st.stop()


if not rows:
    render_empty(
        "No plays are available yet. "
        "Run the DV Sport sync to populate reporting."
    )
    st.stop()


df = pd.DataFrame(rows)

if "is_unusable" not in df.columns:
    df["is_unusable"] = False

unusable_mask = (
    df["is_unusable"]
    .fillna(False)
    .astype(bool)
)

excluded_unusable_total = int(
    unusable_mask.sum()
)

df = df[
    ~unusable_mask
].copy()

if excluded_unusable_total:
    st.caption(
        (
            f"{excluded_unusable_total:,} unusable record"
            f"{'' if excluded_unusable_total == 1 else 's'} "
            "excluded from coordinator reporting."
        )
    )

if df.empty:
    render_empty(
        "No usable records are available for coordinator reporting."
    )
    st.stop()


# ============================================================
# NORMALIZE DATA
# ============================================================

if "match_date" not in df.columns:
    df["match_date"] = None

df["report_date"] = pd.to_datetime(
    df["match_date"],
    errors="coerce",
).dt.date

df["report_play_type"] = df[
    "play_type"
].apply(
    normalized_play_type
)

df["report_status"] = df[
    "review_status"
].apply(
    normalized_review_status
)

df["report_outcome"] = df.apply(
    normalize_outcome,
    axis=1,
)


# ============================================================
# DATE RANGE SELECTOR
# ============================================================

render_section_label(
    "Report Period"
)

valid_dates = [
    value
    for value in df["report_date"].tolist()
    if value is not None
    and not pd.isna(value)
]

today = date.today()

# The normal coordinator workflow is the most recently completed
# Monday-Sunday reporting week.
current_monday = monday_for(today)
previous_monday = (
    current_monday
    - timedelta(days=7)
)

mode = st.radio(
    "Choose report period",
    [
        "Week",
        "Custom Date Range",
    ],
    horizontal=True,
    key="weekly_report_period_mode",
)


if mode == "Week":
    if valid_dates:
        earliest_monday = monday_for(
            min(valid_dates)
        )
        latest_monday = max(
            current_monday,
            monday_for(
                max(valid_dates)
            ),
        )
    else:
        earliest_monday = (
            previous_monday
            - timedelta(
                weeks=8
            )
        )
        latest_monday = current_monday

    # Give some breathing room around the actual data so an
    # empty nearby week can still be intentionally selected.
    earliest_monday = min(
        earliest_monday,
        previous_monday
        - timedelta(
            weeks=8
        ),
    )

    week_starts = []

    cursor = latest_monday

    while cursor >= earliest_monday:
        week_starts.append(cursor)
        cursor -= timedelta(
            days=7
        )

    default_week = (
        previous_monday
        if previous_monday
        in week_starts
        else week_starts[0]
    )

    default_index = (
        week_starts.index(
            default_week
        )
    )

    selected_monday = st.selectbox(
        "Reporting Week",
        week_starts,
        index=default_index,
        format_func=week_label,
        key="weekly_report_selected_week",
        help=(
            "Each reporting week runs Monday through Sunday."
        ),
    )

    report_start = selected_monday
    report_end = sunday_for(
        selected_monday
    )

else:
    date_col1, date_col2 = st.columns(
        2
    )

    with date_col1:
        report_start = st.date_input(
            "Start Date",
            value=previous_monday,
            format="MM/DD/YYYY",
            key="weekly_report_custom_start",
        )

    with date_col2:
        report_end = st.date_input(
            "End Date",
            value=sunday_for(
                previous_monday
            ),
            format="MM/DD/YYYY",
            key="weekly_report_custom_end",
        )


date_range_valid = (
    report_start
    <= report_end
)

if not date_range_valid:
    st.error(
        "Start Date cannot be after End Date."
    )
    st.stop()


with st.container(
    border=True
):
    st.markdown(
        f"**Report Window:** "
        f"{date_range_caption(report_start, report_end)}"
    )

    if mode == "Week":
        st.caption(
            "Standard weekly report • Monday through Sunday"
        )
    else:
        st.caption(
            "Custom coordinator reporting window"
        )


# ============================================================
# FILTER REPORT DATA
# ============================================================

period_df = df[
    (
        df["report_date"]
        >= report_start
    )
    & (
        df["report_date"]
        <= report_end
    )
].copy()


if period_df.empty:
    render_empty(
        "No plays were found in the selected reporting period."
    )
    st.stop()


challenge_df = period_df[
    period_df[
        "report_play_type"
    ]
    == "Challenge"
].copy()

poi_df = period_df[
    period_df[
        "report_play_type"
    ]
    == "POI"
].copy()


# ============================================================
# REPORT INVENTORY
# ============================================================

render_section_label(
    "Report Inventory"
)

total_plays = len(period_df)
total_challenges = len(
    challenge_df
)
total_pois = len(
    poi_df
)

complete_challenges = int(
    (
        challenge_df[
            "report_status"
        ]
        == "Complete"
    ).sum()
)

needs_review_challenges = int(
    (
        challenge_df[
            "report_status"
        ]
        == "Needs Review"
    ).sum()
)

not_viewed_challenges = int(
    (
        challenge_df[
            "report_status"
        ]
        == "Not Viewed"
    ).sum()
)

unfinished_challenges = (
    total_challenges
    - complete_challenges
)

k1, k2, k3, k4, k5 = st.columns(
    5
)

with k1:
    render_kpi(
        "Challenges",
        f"{total_challenges:,}",
        "Coordinator report inventory",
        "ncaa",
    )

with k2:
    render_kpi(
        "POIs",
        f"{total_pois:,}",
        "Plays of interest",
        "purple",
    )

with k3:
    render_kpi(
        "Complete",
        f"{complete_challenges:,}",
        "Completed challenges",
        "green",
    )

with k4:
    render_kpi(
        "Needs Review",
        f"{needs_review_challenges:,}",
        "Challenges flagged",
        "purple",
    )

with k5:
    render_kpi(
        "Not Viewed",
        f"{not_viewed_challenges:,}",
        "Challenges remaining",
        "blue",
    )


# ============================================================
# REPORT READINESS
# ============================================================

render_section_label(
    "Coordinator Report Readiness"
)

if total_challenges == 0:
    st.info(
        "There are no challenges in this reporting period."
    )

elif unfinished_challenges == 0:
    st.success(
        (
            "All challenges in this reporting period are Complete. "
            "This period is ready for coordinator reporting."
        ),
        icon="✅",
    )

else:
    completion_rate = (
        complete_challenges
        / total_challenges
    )

    st.progress(
        completion_rate
    )

    st.warning(
        (
            f"{unfinished_challenges:,} of "
            f"{total_challenges:,} challenges are not yet Complete. "
            "The coordinator report should not be finalized until "
            "every challenge in the selected period is Complete."
        ),
        icon="⚠️",
    )


# ============================================================
# CHALLENGE METRICS
# ============================================================

render_section_label(
    "Challenge Metrics"
)

if challenge_df.empty:
    st.caption(
        "No challenge metrics are available for this period."
    )

else:
    reversed_count = int(
        (
            challenge_df[
                "report_outcome"
            ]
            == "REVERSED"
        ).sum()
    )

    confirmed_count = int(
        (
            challenge_df[
                "report_outcome"
            ]
            == "CONFIRMED"
        ).sum()
    )

    stands_count = int(
        (
            challenge_df[
                "report_outcome"
            ]
            == "STANDS"
        ).sum()
    )

    failure_count = int(
        (
            challenge_df[
                "report_outcome"
            ]
            == "MECHANICAL / VIDEO FAILURE"
        ).sum()
    )

    reversal_rate = (
        reversed_count
        / total_challenges
        * 100
        if total_challenges
        else 0.0
    )

    durations = pd.to_numeric(
        challenge_df.get(
            "challenge_length_seconds",
            pd.Series(
                dtype="float64"
            ),
        ),
        errors="coerce",
    ).dropna()

    average_seconds = (
        int(round(
            durations.mean()
        ))
        if not durations.empty
        else None
    )

    m1, m2, m3, m4, m5, m6 = st.columns(
        6
    )

    with m1:
        render_kpi(
            "Reversal Rate",
            f"{reversal_rate:.1f}%",
            f"{reversed_count:,} reversed",
            "ncaa",
        )

    with m2:
        render_kpi(
            "Reversed",
            f"{reversed_count:,}",
            "Challenges",
            "purple",
        )

    with m3:
        render_kpi(
            "Confirmed",
            f"{confirmed_count:,}",
            "Challenges",
            "green",
        )

    with m4:
        render_kpi(
            "Stands",
            f"{stands_count:,}",
            "Challenges",
            "blue",
        )

    with m5:
        render_kpi(
            "Video / Mechanical",
            f"{failure_count:,}",
            "Failures",
            "purple",
        )

    with m6:
        render_kpi(
            "Avg. Review",
            format_seconds(
                average_seconds
            ),
            "Challenge duration",
            "ncaa",
        )


# ============================================================
# SPECIAL COORDINATOR NOTES
# ============================================================

render_section_label(
    "Special Coordinator Notes"
)

special_notes_df = period_df[
    period_df[
        "weekly_summary_note"
    ]
    .fillna("")
    .astype(str)
    .str.strip()
    != ""
].copy()


if special_notes_df.empty:
    st.caption(
        "No plays in this period have a special weekly summary note."
    )

else:
    special_notes_df = (
        special_notes_df
        .sort_values(
            [
                "report_date",
                "match_name",
            ],
            ascending=[
                True,
                True,
            ],
        )
    )

    for _, row in special_notes_df.iterrows():
        with st.container(
            border=True
        ):
            st.markdown(
                (
                    f"**{clean_text(row.get('match_name')) or 'Match'}** "
                    f"• {row.get('report_play_type', 'Play')} "
                    f"• {row.get('report_date')}"
                )
            )

            details = []

            if clean_text(
                row.get("set_number")
            ):
                details.append(
                    f"Set {row.get('set_number')}"
                )

            if clean_text(
                row.get("score")
            ):
                details.append(
                    str(
                        row.get("score")
                    )
                )

            if details:
                st.caption(
                    " • ".join(details)
                )

            st.write(
                clean_text(
                    row.get(
                        "weekly_summary_note"
                    )
                )
            )


# ============================================================
# ALL CHALLENGES
# ============================================================

render_section_label(
    "All Challenges in Report"
)

if challenge_df.empty:
    render_empty(
        "No challenges are included in the selected period."
    )

else:
    challenge_table = (
        challenge_df
        .copy()
        .sort_values(
            [
                "report_date",
                "conference",
                "match_name",
                "set_number",
            ],
            ascending=[
                True,
                True,
                True,
                True,
            ],
        )
    )

    display = pd.DataFrame(
        {
            "Date":
                challenge_table[
                    "report_date"
                ],

            "Conference":
                challenge_table[
                    "conference"
                ],

            "Match":
                challenge_table[
                    "match_name"
                ],

            "Set":
                challenge_table[
                    "set_number"
                ],

            "Score":
                challenge_table[
                    "score"
                ],

            "Challenging Team":
                challenge_table[
                    "challenging_team"
                ],

            "CRS Category":
                challenge_table[
                    "crs_category"
                ],

            "Original Decision":
                challenge_table[
                    "crs_original_decision"
                ],

            "Outcome":
                challenge_table[
                    "report_outcome"
                ],

            "Review Length":
                challenge_table[
                    "challenge_length_seconds"
                ].apply(
                    format_seconds
                ),

            "Review Status":
                challenge_table[
                    "report_status"
                ],

            "Coordinator Note":
                challenge_table[
                    "weekly_summary_note"
                ],
        }
    )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# POI SUMMARY
# ============================================================

if not poi_df.empty:
    render_section_label(
        "Plays of Interest"
    )

    poi_display = (
        poi_df[
            [
                "report_date",
                "conference",
                "match_name",
                "set_number",
                "score",
                "review_status",
                "weekly_summary_note",
            ]
        ]
        .copy()
        .sort_values(
            [
                "report_date",
                "conference",
                "match_name",
            ]
        )
    )

    poi_display.columns = [
        "Date",
        "Conference",
        "Match",
        "Set",
        "Score",
        "Review Status",
        "Coordinator Note",
    ]

    st.dataframe(
        poi_display,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# REPORT PERIOD SUMMARY
# ============================================================

st.divider()

st.caption(
    (
        f"Coordinator report window: "
        f"{report_start:%m/%d/%Y} – "
        f"{report_end:%m/%d/%Y} • "
        f"{total_challenges:,} challenges • "
        f"{total_pois:,} POIs"
    )
)
