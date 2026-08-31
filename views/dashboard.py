
import altair as alt
import pandas as pd
import streamlit as st

from services.database import get_supabase
from services.ui import (
    NCAA_BLUE,
    SKY,
    MINT,
    LAVENDER,
    MUTED,
    render_page_header,
    render_kpi,
    render_section_label,
    render_empty,
)


# ============================================================
# HEADER
# ============================================================

render_page_header(
    "Review Intelligence",
    (
        "Live post-match review metrics, workflow progress, "
        "challenge trends, faults, and plays of interest across your "
        "active conferences."
    ),
    eyebrow="NCAA WVB • 2026 REVIEW CENTER",
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

    if text.lower() == "complete":
        return "Complete"

    if text.lower() == "needs review":
        return "Needs Review"

    if text.lower() == "not viewed":
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


def is_reversed(row):
    return normalize_outcome(row) == "REVERSED"


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
            desc=False,
        )
        .execute()
    )

    rows = response.data or []

except Exception as exc:
    st.error(
        "Could not load dashboard data."
    )
    st.exception(exc)
    st.stop()


if not rows:
    render_empty(
        "No plays are available yet. "
        "Run the DV Sport sync to populate the dashboard."
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

excluded_unusable_count = int(
    unusable_mask.sum()
)

df = df[
    ~unusable_mask
].copy()

if excluded_unusable_count:
    st.caption(
        (
            f"{excluded_unusable_count:,} unusable record"
            f"{'' if excluded_unusable_count == 1 else 's'} "
            "excluded from all dashboard metrics and analysis."
        )
    )

if df.empty:
    render_empty(
        (
            "All available records are marked unusable, "
            "so there is nothing to include in dashboard analysis."
        )
    )
    st.stop()


# ============================================================
# EXPECTED COLUMNS
# ============================================================

expected_columns = [
    "conference",
    "play_type",
    "review_status",
    "crs_category",
    "ncaa_challenge_category",
    "play_category",
    "dvsport_play_category",
    "is_starred",
    "crs_outcome",
    "challenge_result",
    "match_date",
]

for column in expected_columns:
    if column not in df.columns:
        df[column] = None


# ============================================================
# NORMALIZED FIELDS
# ============================================================

df["dashboard_play_type"] = (
    df["play_type"]
    .apply(normalized_play_type)
)

df["dashboard_status"] = (
    df["review_status"]
    .apply(normalized_review_status)
)

df["dashboard_conference"] = (
    df["conference"]
    .apply(clean_text)
    .replace(
        "",
        "Unknown",
    )
)


# ============================================================
# FILTERS
# ============================================================

render_section_label(
    "Dashboard Filters"
)

filter1, filter2, filter3 = st.columns(
    [
        1.25,
        1.0,
        1.0,
    ]
)

conference_values = sorted(
    {
        value
        for value in df[
            "dashboard_conference"
        ]
        if value != "Unknown"
    }
)

with filter1:
    conference_filter = st.selectbox(
        "Conference",
        [
            "All"
        ]
        + conference_values,
    )

with filter2:
    play_type_filter = st.selectbox(
        "Play Type",
        [
            "All Plays",
            "Challenges",
            "POIs",
            "FAULTS",
        ],
    )

with filter3:
    status_filter = st.selectbox(
        "Review Status",
        [
            "All",
            "Not Viewed",
            "Needs Review",
            "Complete",
        ],
    )


# ============================================================
# APPLY FILTERS
# ============================================================

filtered = df.copy()

if conference_filter != "All":
    filtered = filtered[
        filtered[
            "dashboard_conference"
        ]
        == conference_filter
    ]

if play_type_filter == "Challenges":
    filtered = filtered[
        filtered[
            "dashboard_play_type"
        ]
        == "Challenge"
    ]

elif play_type_filter == "POIs":
    filtered = filtered[
        filtered[
            "dashboard_play_type"
        ]
        == "POI"
    ]

elif play_type_filter == "FAULTS":
    filtered = filtered[
        filtered[
            "dashboard_play_type"
        ]
        == "Fault"
    ]

if status_filter != "All":
    filtered = filtered[
        filtered[
            "dashboard_status"
        ]
        == status_filter
    ]


challenge_df = filtered[
    filtered[
        "dashboard_play_type"
    ]
    == "Challenge"
].copy()

poi_df = filtered[
    filtered[
        "dashboard_play_type"
    ]
    == "POI"
].copy()

fault_df = filtered[
    filtered[
        "dashboard_play_type"
    ]
    == "Fault"
].copy()


# ============================================================
# KPI CALCULATIONS
# ============================================================

total_plays = len(filtered)
total_challenges = len(challenge_df)
total_pois = len(poi_df)
total_faults = len(fault_df)

complete = int(
    (
        filtered[
            "dashboard_status"
        ]
        == "Complete"
    ).sum()
)

needs_review = int(
    (
        filtered[
            "dashboard_status"
        ]
        == "Needs Review"
    ).sum()
)

not_viewed = int(
    (
        filtered[
            "dashboard_status"
        ]
        == "Not Viewed"
    ).sum()
)

completion_rate = (
    complete
    / total_plays
    * 100
    if total_plays
    else 0
)

reversed_count = 0

if total_challenges:
    reversed_count = int(
        challenge_df
        .apply(
            is_reversed,
            axis=1,
        )
        .sum()
    )

reversal_rate = (
    reversed_count
    / total_challenges
    * 100
    if total_challenges
    else 0
)

reviewed_challenges = int(
    (
        challenge_df[
            "dashboard_status"
        ]
        == "Complete"
    ).sum()
)

challenge_completion_rate = (
    reviewed_challenges
    / total_challenges
    * 100
    if total_challenges
    else 0
)


# ============================================================
# PRIMARY KPI ROW
# ============================================================

render_section_label(
    "Review Inventory"
)

k1, k2, k3, k4, k5, k6, k7 = st.columns(
    7
)

with k1:
    render_kpi(
        "Total Plays",
        f"{total_plays:,}",
        "Challenges + POIs + FAULTS",
        "ncaa",
    )

with k2:
    render_kpi(
        "Challenges",
        f"{total_challenges:,}",
        "Replay reviews",
        "blue",
    )

with k3:
    render_kpi(
        "POIs",
        f"{total_pois:,}",
        "Plays of interest",
        "purple",
    )

with k4:
    render_kpi(
        "FAULTS",
        f"{total_faults:,}",
        "Imported fault clips",
        "green",
    )

with k5:
    render_kpi(
        "Complete",
        f"{complete:,}",
        f"{completion_rate:.1f}% of visible plays",
        "green",
    )

with k6:
    render_kpi(
        "Needs Review",
        f"{needs_review:,}",
        "Flagged for another look",
        "purple",
    )

with k7:
    render_kpi(
        "Not Viewed",
        f"{not_viewed:,}",
        "Remaining in queue",
        "blue",
    )


# ============================================================
# SECONDARY KPI ROW
# ============================================================

st.write("")

render_section_label(
    "Challenge Metrics"
)

m1, m2, m3 = st.columns(
    3
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
        "Reversed Challenges",
        f"{reversed_count:,}",
        (
            f"Out of {total_challenges:,} "
            "visible challenges"
        ),
        "purple",
    )

with m3:
    render_kpi(
        "Challenge Completion",
        f"{challenge_completion_rate:.1f}%",
        (
            f"{reviewed_challenges:,} "
            f"of {total_challenges:,}"
        ),
        "green",
    )


# ============================================================
# REVIEW COMPLETION
# ============================================================

st.write("")

render_section_label(
    "Review Completion"
)

if total_plays:
    st.progress(
        min(
            max(
                completion_rate / 100,
                0.0,
            ),
            1.0,
        )
    )

    st.caption(
        f"{complete:,} of {total_plays:,} visible plays "
        f"are complete ({completion_rate:.1f}%)."
    )

else:
    st.caption(
        "No plays match the current filters."
    )


# ============================================================
# ANALYTICS
# ============================================================

st.write("")

render_section_label(
    "Analytics"
)

chart_left, chart_right = st.columns(
    2
)


# ============================================================
# PLAYS BY TYPE
# ============================================================

with chart_left:
    st.subheader(
        "Plays by Type"
    )

    type_data = (
        filtered[
            "dashboard_play_type"
        ]
        .value_counts()
        .rename_axis(
            "Play Type"
        )
        .reset_index(
            name="Plays"
        )
    )

    if not type_data.empty:
        type_order = [
            "Challenge",
            "POI",
            "Fault",
        ]

        type_colors = alt.Scale(
            domain=type_order,
            range=[
                SKY,
                LAVENDER,
                MINT,
            ],
        )

        type_chart = (
            alt.Chart(
                type_data
            )
            .mark_bar(
                cornerRadiusTopLeft=6,
                cornerRadiusTopRight=6,
            )
            .encode(
                x=alt.X(
                    "Play Type:N",
                    sort=type_order,
                    title=None,
                    axis=alt.Axis(
                        labelAngle=0
                    ),
                ),
                y=alt.Y(
                    "Plays:Q",
                    title=None,
                ),
                color=alt.Color(
                    "Play Type:N",
                    scale=type_colors,
                    legend=None,
                ),
                tooltip=[
                    "Play Type:N",
                    "Plays:Q",
                ],
            )
            .properties(
                height=280
            )
        )

        st.altair_chart(
            type_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No play data available."
        )


# ============================================================
# PLAYS BY CONFERENCE
# ============================================================

with chart_right:
    st.subheader(
        "Plays by Conference"
    )

    conference_chart_data = (
        filtered[
            "dashboard_conference"
        ]
        .value_counts()
        .rename_axis(
            "Conference"
        )
        .reset_index(
            name="Plays"
        )
    )

    if not conference_chart_data.empty:
        conference_chart = (
            alt.Chart(
                conference_chart_data
            )
            .mark_bar(
                cornerRadiusTopRight=6,
                cornerRadiusBottomRight=6,
            )
            .encode(
                x=alt.X(
                    "Plays:Q",
                    title=None,
                ),
                y=alt.Y(
                    "Conference:N",
                    sort="-x",
                    title=None,
                ),
                color=alt.value(
                    SKY
                ),
                tooltip=[
                    "Conference:N",
                    "Plays:Q",
                ],
            )
            .properties(
                height=max(
                    240,
                    42
                    * len(
                        conference_chart_data
                    ),
                )
            )
        )

        st.altair_chart(
            conference_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No conference data available."
        )


# ============================================================
# SECOND ANALYTICS ROW
# ============================================================

chart_left2, chart_right2 = st.columns(
    2
)


# ============================================================
# REVIEW WORKFLOW
# ============================================================

with chart_left2:
    st.subheader(
        "Review Workflow"
    )

    status_order = [
        "Complete",
        "Needs Review",
        "Not Viewed",
    ]

    status_data = pd.DataFrame(
        {
            "Status":
                status_order,

            "Count": [
                complete,
                needs_review,
                not_viewed,
            ],
        }
    )

    status_colors = alt.Scale(
        domain=status_order,
        range=[
            MINT,
            LAVENDER,
            MUTED,
        ],
    )

    status_chart = (
        alt.Chart(
            status_data
        )
        .mark_bar(
            cornerRadiusTopLeft=6,
            cornerRadiusTopRight=6,
        )
        .encode(
            x=alt.X(
                "Status:N",
                sort=status_order,
                title=None,
                axis=alt.Axis(
                    labelAngle=0
                ),
            ),
            y=alt.Y(
                "Count:Q",
                title=None,
            ),
            color=alt.Color(
                "Status:N",
                scale=status_colors,
                legend=None,
            ),
            tooltip=[
                "Status:N",
                "Count:Q",
            ],
        )
        .properties(
            height=280
        )
    )

    st.altair_chart(
        status_chart,
        use_container_width=True,
    )


# ============================================================
# CHALLENGES BY CONFERENCE
# ============================================================

with chart_right2:
    st.subheader(
        "Challenges by Conference"
    )

    challenge_conf_data = (
        challenge_df[
            "dashboard_conference"
        ]
        .value_counts()
        .rename_axis(
            "Conference"
        )
        .reset_index(
            name="Challenges"
        )
    )

    if not challenge_conf_data.empty:
        challenge_conf_chart = (
            alt.Chart(
                challenge_conf_data
            )
            .mark_bar(
                cornerRadiusTopRight=6,
                cornerRadiusBottomRight=6,
            )
            .encode(
                x=alt.X(
                    "Challenges:Q",
                    title=None,
                ),
                y=alt.Y(
                    "Conference:N",
                    sort="-x",
                    title=None,
                ),
                color=alt.value(
                    NCAA_BLUE
                ),
                tooltip=[
                    "Conference:N",
                    "Challenges:Q",
                ],
            )
            .properties(
                height=max(
                    240,
                    42
                    * len(
                        challenge_conf_data
                    ),
                )
            )
        )

        st.altair_chart(
            challenge_conf_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No challenge data available."
        )


# ============================================================
# CHALLENGE ANALYTICS
# ============================================================

st.write("")

render_section_label(
    "Challenge Analytics"
)

challenge_left, challenge_right = st.columns(
    2
)


# ============================================================
# CHALLENGE CATEGORIES
# ============================================================

with challenge_left:
    st.subheader(
        "Challenge Categories"
    )

    category_data = (
        challenge_df[
            "ncaa_challenge_category"
        ]
        .where(
            challenge_df[
                "ncaa_challenge_category"
            ].apply(clean_text) != "",
            challenge_df[
                "crs_category"
            ],
        )
        .apply(clean_text)
        .replace(
            "",
            "Not Tagged",
        )
        .value_counts()
        .rename_axis(
            "Category"
        )
        .reset_index(
            name="Challenges"
        )
    )

    if not category_data.empty:
        category_chart = (
            alt.Chart(
                category_data
            )
            .mark_bar(
                cornerRadiusTopRight=6,
                cornerRadiusBottomRight=6,
            )
            .encode(
                x=alt.X(
                    "Challenges:Q",
                    title=None,
                ),
                y=alt.Y(
                    "Category:N",
                    sort="-x",
                    title=None,
                ),
                color=alt.value(
                    LAVENDER
                ),
                tooltip=[
                    "Category:N",
                    "Challenges:Q",
                ],
            )
            .properties(
                height=max(
                    240,
                    38
                    * len(
                        category_data
                    ),
                )
            )
        )

        st.altair_chart(
            category_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No challenge category data available."
        )


# ============================================================
# CHALLENGE OUTCOMES
# ============================================================

with challenge_right:
    st.subheader(
        "Challenge Outcomes"
    )

    if not challenge_df.empty:
        normalized_outcomes = (
            challenge_df
            .apply(
                normalize_outcome,
                axis=1,
            )
        )

        outcome_data = (
            normalized_outcomes
            .value_counts()
            .rename_axis(
                "Outcome"
            )
            .reset_index(
                name="Challenges"
            )
        )

        preferred_order = [
            "REVERSED",
            "CONFIRMED",
            "STANDS",
            "MECHANICAL / VIDEO FAILURE",
            "Not Tagged",
        ]

        known = [
            value
            for value
            in preferred_order
            if value
            in outcome_data[
                "Outcome"
            ].tolist()
        ]

        extras = [
            value
            for value
            in outcome_data[
                "Outcome"
            ].tolist()
            if value
            not in known
        ]

        chart_order = (
            known
            + extras
        )

        outcome_chart = (
            alt.Chart(
                outcome_data
            )
            .mark_bar(
                cornerRadiusTopRight=6,
                cornerRadiusBottomRight=6,
            )
            .encode(
                x=alt.X(
                    "Challenges:Q",
                    title=None,
                ),
                y=alt.Y(
                    "Outcome:N",
                    sort=chart_order,
                    title=None,
                ),
                color=alt.value(
                    NCAA_BLUE
                ),
                tooltip=[
                    "Outcome:N",
                    "Challenges:Q",
                ],
            )
            .properties(
                height=max(
                    240,
                    42
                    * len(
                        outcome_data
                    ),
                )
            )
        )

        st.altair_chart(
            outcome_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No challenge outcome data available."
        )


# ============================================================
# PLAY / FAULT CLASSIFICATION ANALYTICS
# ============================================================

st.write("")

render_section_label(
    "Play Classification Analytics"
)

classification_left, classification_right = st.columns(
    2
)

with classification_left:
    st.subheader(
        "All Plays by Review Category"
    )

    classification_series = (
        filtered[
            "play_category"
        ]
        .apply(clean_text)
        .replace(
            "",
            "Not Tagged",
        )
    )

    classification_data = (
        classification_series
        .value_counts()
        .rename_axis(
            "Play Category"
        )
        .reset_index(
            name="Plays"
        )
    )

    if not classification_data.empty:
        classification_chart = (
            alt.Chart(
                classification_data
            )
            .mark_bar(
                cornerRadiusTopRight=6,
                cornerRadiusBottomRight=6,
            )
            .encode(
                x=alt.X(
                    "Plays:Q",
                    title=None,
                ),
                y=alt.Y(
                    "Play Category:N",
                    sort="-x",
                    title=None,
                ),
                color=alt.value(
                    LAVENDER
                ),
                tooltip=[
                    "Play Category:N",
                    "Plays:Q",
                ],
            )
            .properties(
                height=max(
                    280,
                    32
                    * len(
                        classification_data
                    ),
                )
            )
        )

        st.altair_chart(
            classification_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No play-category data available."
        )


with classification_right:
    st.subheader(
        "FAULTS by Conference"
    )

    fault_conf_data = (
        fault_df[
            "dashboard_conference"
        ]
        .value_counts()
        .rename_axis(
            "Conference"
        )
        .reset_index(
            name="FAULTS"
        )
    )

    if not fault_conf_data.empty:
        fault_conf_chart = (
            alt.Chart(
                fault_conf_data
            )
            .mark_bar(
                cornerRadiusTopRight=6,
                cornerRadiusBottomRight=6,
            )
            .encode(
                x=alt.X(
                    "FAULTS:Q",
                    title=None,
                ),
                y=alt.Y(
                    "Conference:N",
                    sort="-x",
                    title=None,
                ),
                color=alt.value(
                    MINT
                ),
                tooltip=[
                    "Conference:N",
                    "FAULTS:Q",
                ],
            )
            .properties(
                height=max(
                    280,
                    42
                    * len(
                        fault_conf_data
                    ),
                )
            )
        )

        st.altair_chart(
            fault_conf_chart,
            use_container_width=True,
        )

    else:
        st.caption(
            "No FAULT records match the current filters."
        )


# ============================================================
# FAVORITES
# ============================================================

st.write("")

render_section_label(
    "Favorites"
)

starred_series = (
    filtered[
        "is_starred"
    ]
    .fillna(False)
    .astype(bool)
)

starred_count = int(
    starred_series.sum()
)

fav1, fav2, fav3, fav4 = st.columns(
    4
)

with fav1:
    render_kpi(
        "Starred Plays",
        f"{starred_count:,}",
        "Favorites in current view",
        "purple",
    )

for column, play_type, label, color in [
    (fav2, "Challenge", "Starred Challenges", "blue"),
    (fav3, "POI", "Starred POIs", "purple"),
    (fav4, "Fault", "Starred FAULTS", "green"),
]:
    with column:
        type_starred = int(
            (
                (
                    filtered[
                        "dashboard_play_type"
                    ]
                    == play_type
                )
                & starred_series
            ).sum()
        )

        render_kpi(
            label,
            f"{type_starred:,}",
            "Favorites",
            color,
        )
