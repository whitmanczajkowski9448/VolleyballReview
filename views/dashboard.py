from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from services.database import get_supabase
from services.review_taxonomy import (
    normalize_challenge_category,
    normalize_outcome,
    normalize_referee_judgment,
    normalize_review_status,
)
from services.ui import (
    NCAA_BLUE,
    SKY,
    MINT,
    LAVENDER,
    render_empty,
    render_kpi,
    render_page_header,
    render_section_label,
)


render_page_header(
    "Review Intelligence",
    "Current review workload and challenge analytics.",
    eyebrow="NCAA WVB • REVIEW CENTER",
)

supabase = get_supabase()


def clean_text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "null", "nan", "<na>"} else text


def play_type(value):
    text = clean_text(value).upper()
    if text in {"CHALLENGE", "CHALLENGES"}:
        return "Challenge"
    if text in {"POI", "POIS", "PLAY OF INTEREST", "PLAYS OF INTEREST"}:
        return "POI"
    if text in {"FAULT", "FAULTS"}:
        return "Fault"
    return clean_text(value) or "Unknown"


def format_seconds(value):
    try:
        total = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"{total // 60}:{total % 60:02d}"


try:
    response = (
        supabase.table("plays")
        .select("*")
        .order("match_date", desc=False)
        .execute()
    )
    rows = response.data or []
except Exception as exc:
    st.error("Could not load dashboard data.")
    st.exception(exc)
    st.stop()

if not rows:
    render_empty("No plays are available yet.")
    st.stop()

df = pd.DataFrame(rows)
if "is_unusable" in df.columns:
    df = df[~df["is_unusable"].fillna(False).astype(bool)].copy()
if df.empty:
    render_empty("No plays are available for analysis.")
    st.stop()

for column in [
    "conference", "play_type", "review_status", "ncaa_challenge_category",
    "crs_category", "crs_outcome", "challenge_result", "referee_judgment",
    "review_decision_correct", "challenge_length_seconds",
    "dvsport_challenge_length_seconds", "is_starred", "match_date",
    "match_name", "set_number", "score", "weekly_summary_note",
]:
    if column not in df.columns:
        df[column] = None

df["type"] = df["play_type"].apply(play_type)
df["status"] = df["review_status"].apply(normalize_review_status)
df["conference_display"] = df["conference"].apply(lambda x: clean_text(x) or "Unknown")
df["date"] = pd.to_datetime(df["match_date"], errors="coerce").dt.date
df["outcome"] = df.apply(
    lambda row: normalize_outcome(row.get("crs_outcome") or row.get("challenge_result")),
    axis=1,
)
df["category"] = df.apply(
    lambda row: normalize_challenge_category(
        row.get("ncaa_challenge_category") or row.get("crs_category")
    ) or "Not Tagged",
    axis=1,
)
df["judgment"] = df.apply(
    lambda row: normalize_referee_judgment(
        row.get("referee_judgment"), row.get("review_decision_correct")
    ) or "Not Tagged",
    axis=1,
)
df["length"] = pd.to_numeric(
    df["challenge_length_seconds"].where(
        df["challenge_length_seconds"].notna(),
        df["dvsport_challenge_length_seconds"],
    ),
    errors="coerce",
)

render_section_label("Dashboard Filters")
conferences = sorted(df["conference_display"].dropna().unique().tolist())

f1, f2, f3, f4 = st.columns(4)
with f1:
    conf_filter = st.selectbox("Conference", ["All"] + conferences, key="dash_conf")
with f2:
    type_filter = st.selectbox("Play Type", ["All", "Challenge", "POI", "Fault"], key="dash_type")
with f3:
    status_filter = st.selectbox(
        "Review Status",
        ["All", "Not Viewed", "Needs Additional Review", "Complete"],
        key="dash_status",
    )
with f4:
    date_filter = st.selectbox(
        "Date Range",
        ["All Dates", "Last 7 Days", "Last 30 Days"],
        key="dash_date",
    )

filtered = df.copy()
if conf_filter != "All":
    filtered = filtered[filtered["conference_display"] == conf_filter]
if type_filter != "All":
    filtered = filtered[filtered["type"] == type_filter]
if status_filter != "All":
    filtered = filtered[filtered["status"] == status_filter]
if date_filter != "All Dates":
    days = 6 if date_filter == "Last 7 Days" else 29
    cutoff = date.today() - timedelta(days=days)
    filtered = filtered[filtered["date"].notna() & (filtered["date"] >= cutoff)]

if filtered.empty:
    render_empty("No plays match the current filters.")
    st.stop()

challenge_df = filtered[filtered["type"] == "Challenge"].copy()
poi_df = filtered[filtered["type"] == "POI"].copy()
fault_df = filtered[filtered["type"] == "Fault"].copy()

total = len(filtered)
challenges = len(challenge_df)
pois = len(poi_df)
faults = len(fault_df)
complete = int((filtered["status"] == "Complete").sum())
needs = int((filtered["status"] == "Needs Additional Review").sum())
not_viewed = int((filtered["status"] == "Not Viewed").sum())

render_section_label("Review Inventory")
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
for col, label, value, tone in [
    (k1, "Total Plays", total, "ncaa"),
    (k2, "Challenges", challenges, "blue"),
    (k3, "POIs", pois, "purple"),
    (k4, "Faults", faults, "green"),
    (k5, "Complete", complete, "green"),
    (k6, "Needs Additional Review", needs, "purple"),
    (k7, "Not Viewed", not_viewed, "blue"),
]:
    with col:
        render_kpi(label, f"{value:,}", "", tone)

if not challenge_df.empty:
    reversed_count = int((challenge_df["outcome"] == "Reversed").sum())
    confirmed_count = int((challenge_df["outcome"] == "Confirmed").sum())
    stands_count = int((challenge_df["outcome"] == "Stands").sum())
    mechanical_count = int((challenge_df["outcome"] == "Mechanical Failure").sum())
    reversal_rate = reversed_count / challenges * 100 if challenges else 0.0
    valid_lengths = challenge_df["length"].dropna()
    avg_length = int(round(valid_lengths.mean())) if not valid_lengths.empty else None
    incorrect = int((challenge_df["judgment"] == "Incorrect").sum())
    unclear = int((challenge_df["judgment"] == "Unclear").sum())

    render_section_label("Challenge Metrics")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        render_kpi("Reversal Rate", f"{reversal_rate:.1f}%", f"{reversed_count} reversed", "ncaa")
    with m2:
        render_kpi("Confirmed", f"{confirmed_count:,}", "", "green")
    with m3:
        render_kpi("Stands", f"{stands_count:,}", "", "blue")
    with m4:
        render_kpi("Avg. Review", format_seconds(avg_length), "", "purple")
    with m5:
        render_kpi("Incorrect / Unclear", f"{incorrect} / {unclear}", "", "ncaa")

    render_section_label("Challenge Analytics")
    left, right = st.columns(2)

    outcome_data = (
        challenge_df["outcome"]
        .replace("", "Not Tagged")
        .value_counts()
        .rename_axis("Outcome")
        .reset_index(name="Challenges")
    )
    with left:
        st.subheader("Challenge Outcomes")
        chart = (
            alt.Chart(outcome_data)
            .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
            .encode(
                x=alt.X("Challenges:Q", title=None),
                y=alt.Y("Outcome:N", sort="-x", title=None),
                color=alt.value(NCAA_BLUE),
                tooltip=["Outcome:N", "Challenges:Q"],
            )
            .properties(height=max(220, 38 * len(outcome_data)))
        )
        st.altair_chart(chart, use_container_width=True)

    category_data = (
        challenge_df["category"]
        .value_counts()
        .rename_axis("Category")
        .reset_index(name="Challenges")
    )
    with right:
        st.subheader("Challenge Categories")
        chart = (
            alt.Chart(category_data)
            .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
            .encode(
                x=alt.X("Challenges:Q", title=None),
                y=alt.Y("Category:N", sort="-x", title=None),
                color=alt.value(SKY),
                tooltip=["Category:N", "Challenges:Q"],
            )
            .properties(height=max(220, 38 * len(category_data)))
        )
        st.altair_chart(chart, use_container_width=True)

    left2, right2 = st.columns(2)
    judgment_data = (
        challenge_df["judgment"]
        .value_counts()
        .rename_axis("Judgment")
        .reset_index(name="Challenges")
    )
    with left2:
        st.subheader("Referee Judgment")
        chart = (
            alt.Chart(judgment_data)
            .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
            .encode(
                x=alt.X("Challenges:Q", title=None),
                y=alt.Y("Judgment:N", sort="-x", title=None),
                color=alt.value(LAVENDER),
                tooltip=["Judgment:N", "Challenges:Q"],
            )
            .properties(height=max(220, 38 * len(judgment_data)))
        )
        st.altair_chart(chart, use_container_width=True)

    conference_data = (
        challenge_df["conference_display"]
        .value_counts()
        .rename_axis("Conference")
        .reset_index(name="Challenges")
    )
    with right2:
        st.subheader("Challenges by Conference")
        chart = (
            alt.Chart(conference_data)
            .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
            .encode(
                x=alt.X("Challenges:Q", title=None),
                y=alt.Y("Conference:N", sort="-x", title=None),
                color=alt.value(MINT),
                tooltip=["Conference:N", "Challenges:Q"],
            )
            .properties(height=max(220, 38 * len(conference_data)))
        )
        st.altair_chart(chart, use_container_width=True)

starred = filtered[filtered["is_starred"] == True].copy()  # noqa: E712
if not starred.empty:
    render_section_label("Starred Plays")
    display = starred[[
        "match_date", "conference_display", "match_name", "type",
        "set_number", "score", "status",
    ]].copy()
    display.columns = ["Date", "Conference", "Match", "Type", "Set", "Score", "Status"]
    st.dataframe(display, use_container_width=True, hide_index=True)
