from datetime import date, timedelta

import pandas as pd
import streamlit as st

from services.auth import require_admin
from services.database import get_supabase
from services.public_share import public_challenge_url
from services.reporting import build_challenge_analytics_pdf
from services.review_taxonomy import (
    normalize_challenge_category,
    normalize_outcome,
    normalize_referee_judgment,
    normalize_review_status,
)
from services.ui import (
    render_empty,
    render_kpi,
    render_page_header,
    render_section_label,
)


require_admin()

render_page_header(
    "Weekly Coordinator Report",
    "Build a concise coordinator brief and a full challenge analytics attachment.",
    eyebrow="NCAA WVB • COORDINATOR REPORTING",
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


def monday_for(day):
    return day - timedelta(days=day.weekday())


def sunday_for(monday):
    return monday + timedelta(days=6)


def week_label(monday):
    return f"{monday:%b %d, %Y} – {sunday_for(monday):%b %d, %Y}"


def format_seconds(value):
    try:
        total = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"{total // 60}:{total % 60:02d}"


def challenge_length_value(row):
    value = row.get("challenge_length_seconds")
    return value if value is not None and not pd.isna(value) else row.get("dvsport_challenge_length_seconds")


def email_subject(start_date, end_date):
    if start_date.year == end_date.year:
        date_text = f"{start_date:%B %d} – {end_date:%B %d, %Y}"
    else:
        date_text = f"{start_date:%B %d, %Y} – {end_date:%B %d, %Y}"
    return f"NCAA WVB Weekly Review | {date_text}"


def build_coordinator_body(
    *,
    report_start,
    report_end,
    total_challenges,
    total_pois,
    total_faults,
    complete,
    needs_review,
    not_viewed,
    reversed_count,
    confirmed_count,
    stands_count,
    mechanical_count,
    reversal_rate,
    average_seconds,
    correct_count,
    incorrect_count,
    unclear_count,
    special_rows,
):
    lines = [
        "Hello,",
        "",
        (
            f"Here is the NCAA Women's Volleyball review update for "
            f"{report_start:%B %d, %Y} through {report_end:%B %d, %Y}."
        ),
        "",
        (
            f"The report includes {total_challenges:,} challenge"
            f"{'' if total_challenges == 1 else 's'}, {total_pois:,} POI"
            f"{'' if total_pois == 1 else 's'}, and {total_faults:,} fault clip"
            f"{'' if total_faults == 1 else 's'}. "
            f"Challenge review status: {complete:,} complete, "
            f"{needs_review:,} needing additional review, and "
            f"{not_viewed:,} not yet viewed."
        ),
    ]

    if total_challenges:
        lines.extend([
            "",
            (
                f"Challenge outcomes: {confirmed_count:,} confirmed, "
                f"{reversed_count:,} reversed, {stands_count:,} stands, and "
                f"{mechanical_count:,} mechanical/video failure"
                f"{'' if mechanical_count == 1 else 's'}. "
                f"The reversal rate is {reversal_rate:.1f}% and the average "
                f"review length is {format_seconds(average_seconds)}."
            ),
            (
                f"Referee judgment: {correct_count:,} correct, "
                f"{incorrect_count:,} incorrect, and {unclear_count:,} unclear."
            ),
        ])

    lines.extend(["", "CHALLENGES REQUIRING ATTENTION"])

    if not special_rows:
        lines.append("No challenges have a special coordinator note for this report.")
    else:
        for index, row in enumerate(special_rows, start=1):
            match_name = clean_text(row.get("match_name")) or "Challenge"
            set_text = clean_text(row.get("set_number")) or "—"
            score = clean_text(row.get("score")) or "—"
            category = clean_text(row.get("category")) or "—"
            outcome = clean_text(row.get("outcome")) or "—"
            note = clean_text(row.get("weekly_summary_note"))
            link = clean_text(row.get("public_url"))

            lines.extend([
                "",
                f"{index}. {match_name} • Set {set_text} • {score}",
                f"   {category} • {outcome}",
                f"   {note}",
            ])
            if link:
                lines.append(f"   View challenge: {link}")

    lines.extend([
        "",
        "A full challenge analytics PDF can be downloaded from VolleyReview and attached for the complete challenge-by-challenge record.",
        "",
        "NCAA Women's Volleyball Review",
    ])
    return "\n".join(lines)


# ============================================================
# LOAD + NORMALIZE
# ============================================================

try:
    response = (
        supabase.table("plays")
        .select("*")
        .order("match_date", desc=True)
        .execute()
    )
    rows = response.data or []
except Exception as exc:
    st.error("Could not load coordinator report data.")
    st.exception(exc)
    st.stop()

if not rows:
    render_empty("No plays are available yet.")
    st.stop()

df = pd.DataFrame(rows)
if "is_unusable" in df.columns:
    df = df[~df["is_unusable"].fillna(False).astype(bool)].copy()
if df.empty:
    render_empty("No plays are available for reporting.")
    st.stop()

for column in [
    "match_date", "conference", "play_type", "review_status", "crs_outcome",
    "challenge_result", "ncaa_challenge_category", "crs_category",
    "crs_original_decision", "challenge_outcome_detail", "referee_judgment",
    "review_decision_correct", "challenge_length_seconds",
    "dvsport_challenge_length_seconds", "weekly_summary_note", "match_name",
    "set_number", "score", "challenging_team", "is_starred",
]:
    if column not in df.columns:
        df[column] = None

df["report_date"] = pd.to_datetime(df["match_date"], errors="coerce").dt.date
df["report_type"] = df["play_type"].apply(play_type)
df["report_status"] = df["review_status"].apply(normalize_review_status)
df["report_conference"] = df["conference"].apply(lambda x: clean_text(x) or "No Conference")
df["report_outcome"] = df.apply(
    lambda row: normalize_outcome(row.get("crs_outcome") or row.get("challenge_result")), axis=1
)
df["report_category"] = df.apply(
    lambda row: normalize_challenge_category(
        row.get("ncaa_challenge_category") or row.get("crs_category")
    ) or "Not Tagged",
    axis=1,
)
df["report_judgment"] = df.apply(
    lambda row: normalize_referee_judgment(
        row.get("referee_judgment"), row.get("review_decision_correct")
    ) or "Not Tagged",
    axis=1,
)


# ============================================================
# REPORT PERIOD
# ============================================================

render_section_label("Report Period")
valid_dates = [x for x in df["report_date"].tolist() if x is not None and not pd.isna(x)]
today = date.today()
current_monday = monday_for(today)
previous_monday = current_monday - timedelta(days=7)

mode = st.radio(
    "Report Period",
    ["Week", "Custom Date Range"],
    horizontal=True,
    key="weekly_period_mode",
    label_visibility="collapsed",
)

if mode == "Week":
    earliest = monday_for(min(valid_dates)) if valid_dates else previous_monday - timedelta(weeks=8)
    latest = max(current_monday, monday_for(max(valid_dates))) if valid_dates else current_monday
    earliest = min(earliest, previous_monday - timedelta(weeks=8))
    weeks = []
    cursor = latest
    while cursor >= earliest:
        weeks.append(cursor)
        cursor -= timedelta(days=7)
    default_week = previous_monday if previous_monday in weeks else weeks[0]
    selected_monday = st.selectbox(
        "Reporting Week",
        weeks,
        index=weeks.index(default_week),
        format_func=week_label,
        key="weekly_selected_week",
    )
    report_start = selected_monday
    report_end = sunday_for(selected_monday)
else:
    d1, d2 = st.columns(2)
    with d1:
        report_start = st.date_input(
            "Start Date",
            value=previous_monday,
            format="MM/DD/YYYY",
            key="weekly_custom_start",
        )
    with d2:
        report_end = st.date_input(
            "End Date",
            value=sunday_for(previous_monday),
            format="MM/DD/YYYY",
            key="weekly_custom_end",
        )

if report_start > report_end:
    st.error("Start Date cannot be after End Date.")
    st.stop()

date_df = df[
    df["report_date"].notna()
    & (df["report_date"] >= report_start)
    & (df["report_date"] <= report_end)
].copy()

if date_df.empty:
    render_empty("No plays were found in the selected report period.")
    st.stop()


# ============================================================
# FILTERS
# ============================================================

render_section_label("Report Filters")
conference_options = sorted(date_df["report_conference"].dropna().unique().tolist())
type_options = [x for x in ["Challenge", "POI", "Fault"] if x in set(date_df["report_type"])]
status_options = [
    x for x in ["Complete", "Needs Additional Review", "Not Viewed"]
    if x in set(date_df["report_status"])
]


def prune_multiselect_state(key, options):
    """Keep saved filters valid when a different date window changes options."""
    if key not in st.session_state:
        return
    existing = st.session_state.get(key)
    if not isinstance(existing, list):
        st.session_state.pop(key, None)
        return
    cleaned = [item for item in existing if item in options]
    if existing and not cleaned:
        cleaned = list(options)
    st.session_state[key] = cleaned


prune_multiselect_state("weekly_conferences", conference_options)
prune_multiselect_state("weekly_types", type_options)
prune_multiselect_state("weekly_statuses", status_options)

f1, f2, f3 = st.columns(3)
with f1:
    selected_conferences = st.multiselect(
        "Conference",
        conference_options,
        default=conference_options,
        key="weekly_conferences",
    )
with f2:
    selected_types = st.multiselect(
        "Type of Play",
        type_options,
        default=type_options,
        key="weekly_types",
    )
with f3:
    selected_statuses = st.multiselect(
        "Review Status",
        status_options,
        default=status_options,
        key="weekly_statuses",
    )

if not selected_conferences or not selected_types or not selected_statuses:
    render_empty("Select at least one conference, play type, and review status.")
    st.stop()

period_df = date_df[
    date_df["report_conference"].isin(selected_conferences)
    & date_df["report_type"].isin(selected_types)
    & date_df["report_status"].isin(selected_statuses)
].copy()

if period_df.empty:
    render_empty("No plays match the selected report filters.")
    st.stop()

challenge_df = period_df[period_df["report_type"] == "Challenge"].copy()
poi_df = period_df[period_df["report_type"] == "POI"].copy()
fault_df = period_df[period_df["report_type"] == "Fault"].copy()


# ============================================================
# COORDINATOR BRIEF
# ============================================================

total_challenges = len(challenge_df)
total_pois = len(poi_df)
total_faults = len(fault_df)
complete = int((challenge_df["report_status"] == "Complete").sum())
needs_review = int((challenge_df["report_status"] == "Needs Additional Review").sum())
not_viewed = int((challenge_df["report_status"] == "Not Viewed").sum())
reversed_count = int((challenge_df["report_outcome"] == "Reversed").sum())
confirmed_count = int((challenge_df["report_outcome"] == "Confirmed").sum())
stands_count = int((challenge_df["report_outcome"] == "Stands").sum())
mechanical_count = int((challenge_df["report_outcome"] == "Mechanical Failure").sum())
reversal_rate = reversed_count / total_challenges * 100 if total_challenges else 0.0
correct_count = int((challenge_df["report_judgment"] == "Correct").sum())
incorrect_count = int((challenge_df["report_judgment"] == "Incorrect").sum())
unclear_count = int((challenge_df["report_judgment"] == "Unclear").sum())

lengths = []
for _, row in challenge_df.iterrows():
    value = challenge_length_value(row)
    try:
        lengths.append(int(value))
    except (TypeError, ValueError):
        pass
average_seconds = int(round(sum(lengths) / len(lengths))) if lengths else None

render_section_label("Coordinator Brief")
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    render_kpi("Challenges", f"{total_challenges:,}", "", "ncaa")
with k2:
    render_kpi("Complete", f"{complete:,}", "", "green")
with k3:
    render_kpi("Needs Additional Review", f"{needs_review:,}", "", "purple")
with k4:
    render_kpi("Reversal Rate", f"{reversal_rate:.1f}%", "", "blue")
with k5:
    render_kpi("Avg. Review", format_seconds(average_seconds), "", "ncaa")

if total_challenges:
    st.markdown(
        f"**{confirmed_count:,} confirmed • {reversed_count:,} reversed • "
        f"{stands_count:,} stands • {mechanical_count:,} mechanical failure**  "
        f"  \nReferee judgment: **{correct_count:,} correct • {incorrect_count:,} incorrect • {unclear_count:,} unclear**"
    )


# ============================================================
# PUBLIC LINKS + SPECIAL NOTES
# ============================================================

challenge_rows = []
for _, row in challenge_df.sort_values(
    ["report_date", "conference", "match_name", "set_number"],
    ascending=[True, True, True, True],
).iterrows():
    public_url = public_challenge_url(row.get("id"))
    challenge_rows.append({
        "id": row.get("id"),
        "match_date": clean_text(row.get("match_date")),
        "conference": clean_text(row.get("conference")),
        "match_name": clean_text(row.get("match_name")),
        "set_number": clean_text(row.get("set_number")),
        "score": clean_text(row.get("score")),
        "category": clean_text(row.get("report_category")),
        "original_call": clean_text(row.get("crs_original_decision")),
        "outcome": clean_text(row.get("report_outcome")),
        "outcome_detail": clean_text(row.get("challenge_outcome_detail")),
        "judgment": clean_text(row.get("report_judgment")),
        "length_seconds": challenge_length_value(row),
        "status": clean_text(row.get("report_status")),
        "weekly_summary_note": clean_text(row.get("weekly_summary_note")),
        "public_url": public_url,
    })

special_rows = [row for row in challenge_rows if clean_text(row.get("weekly_summary_note"))]

render_section_label("Challenges Requiring Attention")
if not special_rows:
    st.success("No challenges have a special coordinator note for this report.")
else:
    for row in special_rows:
        with st.container(border=True):
            left, right = st.columns([5, 1.15])
            with left:
                st.markdown(
                    f"**{row['match_name'] or 'Challenge'}** • "
                    f"{row['conference'] or '—'} • Set {row['set_number'] or '—'} • {row['score'] or '—'}"
                )
                st.caption(
                    f"{row['category'] or '—'} • {row['outcome'] or '—'} • {row['judgment'] or '—'}"
                )
                st.write(row["weekly_summary_note"])
            with right:
                if row["public_url"]:
                    st.link_button(
                        "Open Challenge ↗",
                        row["public_url"],
                        use_container_width=True,
                    )


# ============================================================
# FULL ANALYTICS PDF
# ============================================================

render_section_label("Full Challenge Analytics")
if challenge_rows:
    category_counts = {}
    for row in challenge_rows:
        category = row.get("category") or "Not Tagged"
        category_counts[category] = category_counts.get(category, 0) + 1

    pdf_summary = {
        "total": total_challenges,
        "complete": complete,
        "needs_review": needs_review,
        "reversed": reversed_count,
        "confirmed": confirmed_count,
        "stands": stands_count,
        "mechanical": mechanical_count,
        "reversal_rate": reversal_rate,
        "average_seconds": average_seconds,
        "incorrect": incorrect_count,
        "unclear": unclear_count,
        "category_counts": category_counts,
    }

    try:
        pdf_bytes = build_challenge_analytics_pdf(
            challenge_rows,
            report_start=report_start,
            report_end=report_end,
            conferences=selected_conferences,
            statuses=selected_statuses,
            summary=pdf_summary,
        )
        filename = (
            f"VolleyReview_Challenge_Analytics_"
            f"{report_start:%Y%m%d}_{report_end:%Y%m%d}.pdf"
        )
        st.download_button(
            "⬇ Download Full Challenge Analytics PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    except Exception as exc:
        st.error("The analytics PDF could not be generated.")
        st.exception(exc)
else:
    st.info("No challenges are included in the selected filters.")


# ============================================================
# COPY-READY COORDINATOR EMAIL
# ============================================================

render_section_label("Copy-Ready Coordinator Email")
subject = email_subject(report_start, report_end)
body = build_coordinator_body(
    report_start=report_start,
    report_end=report_end,
    total_challenges=total_challenges,
    total_pois=total_pois,
    total_faults=total_faults,
    complete=complete,
    needs_review=needs_review,
    not_viewed=not_viewed,
    reversed_count=reversed_count,
    confirmed_count=confirmed_count,
    stands_count=stands_count,
    mechanical_count=mechanical_count,
    reversal_rate=reversal_rate,
    average_seconds=average_seconds,
    correct_count=correct_count,
    incorrect_count=incorrect_count,
    unclear_count=unclear_count,
    special_rows=special_rows,
)

with st.container(border=True):
    st.markdown("**Subject**")
    st.code(subject, language="text", wrap_lines=True)
    st.markdown("**Email Body**")
    st.code(body, language="text", wrap_lines=True)
