from datetime import date, timedelta

import pandas as pd
import streamlit as st

from services.database import get_supabase
from services.auth import require_admin
from services.challenge_email import (
    dedupe_addresses,
    gmail_compose_url,
    load_saved_recipients,
    recipient_label,
    split_manual_addresses,
)
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
# WEEKLY EMAIL HELPERS
# ============================================================

def report_default_recipient_ids(
    recipients,
    conferences,
):
    conference_set = {
        clean_text(value).upper()
        for value in conferences
        if clean_text(value)
    }

    defaults = []

    for recipient in recipients:
        if not recipient.get("is_default"):
            continue

        recipient_conference = clean_text(
            recipient.get("conference")
        ).upper()

        if (
            not recipient_conference
            or recipient_conference in {"ALL", "NATIONAL"}
            or recipient_conference in conference_set
        ):
            recipient_id = recipient.get("id")
            if recipient_id is not None:
                defaults.append(str(recipient_id))

    return defaults


def weekly_email_subject(
    report_start,
    report_end,
):
    if report_start == report_end:
        date_text = f"{report_start:%B %d, %Y}"
    elif report_start.year == report_end.year:
        date_text = (
            f"{report_start:%B %d} – "
            f"{report_end:%B %d, %Y}"
        )
    else:
        date_text = (
            f"{report_start:%B %d, %Y} – "
            f"{report_end:%B %d, %Y}"
        )

    return f"NCAA WVB Weekly Review | {date_text}"


def email_value(value, fallback="—"):
    text = clean_text(value)
    return text if text else fallback


def build_weekly_email_body(
    report_start,
    report_end,
    challenge_df,
    poi_df,
    fault_df,
    total_challenges,
    total_pois,
    total_faults,
    complete_challenges,
    needs_review_challenges,
    not_viewed_challenges,
    reversed_count,
    confirmed_count,
    stands_count,
    failure_count,
    reversal_rate,
    average_seconds,
    custom_message="",
    include_challenge_details=True,
    include_poi_fault_details=True,
):
    lines = [
        "NCAA WOMEN'S VOLLEYBALL WEEKLY REVIEW",
        "=" * 44,
        f"Report period: {report_start:%B %d, %Y} through {report_end:%B %d, %Y}",
        "",
    ]

    if clean_text(custom_message):
        lines.extend([
            clean_text(custom_message),
            "",
        ])

    lines.extend([
        "REPORT INVENTORY",
        "-" * 20,
        f"Challenges: {total_challenges:,}",
        f"Plays of Interest: {total_pois:,}",
        f"Faults: {total_faults:,}",
        "",
        "CHALLENGE REVIEW STATUS",
        "-" * 24,
        f"Complete: {complete_challenges:,}",
        f"Needs Review: {needs_review_challenges:,}",
        f"Not Viewed: {not_viewed_challenges:,}",
        "",
        "CHALLENGE METRICS",
        "-" * 19,
        f"Reversal rate: {reversal_rate:.1f}%",
        f"Reversed: {reversed_count:,}",
        f"Confirmed: {confirmed_count:,}",
        f"Stands: {stands_count:,}",
        f"Mechanical / video failure: {failure_count:,}",
        f"Average review length: {format_seconds(average_seconds)}",
        "",
    ])

    notes_df = pd.concat(
        [
            challenge_df,
            poi_df,
            fault_df,
        ],
        ignore_index=False,
    )

    notes_df = notes_df[
        notes_df.get(
            "weekly_summary_note",
            pd.Series(index=notes_df.index, dtype="object"),
        )
        .fillna("")
        .astype(str)
        .str.strip()
        != ""
    ].copy()

    if not notes_df.empty:
        lines.extend([
            "SPECIAL COORDINATOR NOTES",
            "-" * 25,
        ])

        notes_df = notes_df.sort_values(
            ["report_date", "match_name"],
            ascending=[True, True],
        )

        for _, row in notes_df.iterrows():
            play_type = email_value(
                row.get("report_play_type"),
                "Play",
            )
            match_name = email_value(
                row.get("match_name"),
                "Match",
            )
            detail_parts = [
                str(row.get("report_date") or ""),
                play_type,
                match_name,
            ]

            set_text = clean_text(row.get("set_number"))
            score_text = clean_text(row.get("score"))
            if set_text:
                detail_parts.append(f"Set {set_text}")
            if score_text:
                detail_parts.append(score_text)

            lines.append(" • ".join(
                part for part in detail_parts if part
            ))
            lines.append(
                email_value(row.get("weekly_summary_note"))
            )
            lines.append("")

    if include_challenge_details and not challenge_df.empty:
        lines.extend([
            "CHALLENGE-BY-CHALLENGE SUMMARY",
            "-" * 32,
        ])

        challenge_table = challenge_df.sort_values(
            [
                "report_date",
                "conference",
                "match_name",
                "set_number",
            ],
            ascending=[True, True, True, True],
        )

        for index, (_, row) in enumerate(
            challenge_table.iterrows(),
            start=1,
        ):
            date_text = email_value(row.get("report_date"))
            conference = email_value(row.get("conference"))
            match_name = email_value(row.get("match_name"))
            set_text = email_value(row.get("set_number"))
            score_text = email_value(row.get("score"))
            challenger = email_value(row.get("challenging_team"))
            category = email_value(
                row.get("ncaa_challenge_category")
                or row.get("crs_category")
                or row.get("dvsport_crs_category")
            )
            original_decision = email_value(
                row.get("crs_original_decision")
            )
            dvsport_result = email_value(
                row.get("challenge_result")
            )
            outcome = email_value(row.get("report_outcome"))
            review_status = email_value(row.get("report_status"))
            review_length = format_seconds(
                row.get("challenge_length_seconds")
            )
            coordinator_note = clean_text(
                row.get("weekly_summary_note")
            )

            lines.extend([
                f"{index}. {date_text} • {conference} • {match_name}",
                f"   Set {set_text} • Score {score_text} • Challenging Team: {challenger}",
                f"   Category: {category}",
                f"   Original Decision: {original_decision}",
                f"   DV Sport Result: {dvsport_result}",
                f"   VolleyReview Outcome: {outcome}",
                f"   Review Length: {review_length} • Status: {review_status}",
            ])

            if coordinator_note:
                lines.append(
                    f"   Coordinator Note: {coordinator_note}"
                )

            lines.append("")

    if include_poi_fault_details:
        if not poi_df.empty:
            lines.extend([
                "PLAYS OF INTEREST",
                "-" * 17,
            ])

            poi_table = poi_df.sort_values(
                ["report_date", "conference", "match_name"]
            )

            for _, row in poi_table.iterrows():
                lines.append(
                    " • ".join([
                        email_value(row.get("report_date")),
                        email_value(row.get("conference")),
                        email_value(row.get("match_name")),
                        f"Set {email_value(row.get('set_number'))}",
                        email_value(row.get("score")),
                        email_value(row.get("report_status")),
                    ])
                )

                note = clean_text(row.get("weekly_summary_note"))
                if note:
                    lines.append(f"  Note: {note}")

            lines.append("")

        if not fault_df.empty:
            lines.extend([
                "FAULTS",
                "-" * 6,
            ])

            fault_table = fault_df.sort_values(
                ["report_date", "conference", "match_name"]
            )

            for _, row in fault_table.iterrows():
                fault_type = email_value(
                    row.get("play_category")
                    or row.get("dvsport_play_category")
                )

                lines.append(
                    " • ".join([
                        email_value(row.get("report_date")),
                        email_value(row.get("conference")),
                        email_value(row.get("match_name")),
                        f"Set {email_value(row.get('set_number'))}",
                        email_value(row.get("score")),
                        fault_type,
                        email_value(row.get("report_status")),
                    ])
                )

                note = clean_text(row.get("weekly_summary_note"))
                if note:
                    lines.append(f"  Note: {note}")

            lines.append("")

    lines.extend([
        "=" * 44,
        "NCAA Women's Volleyball Review",
    ])

    return "\n".join(lines)


@st.dialog(
    "Generate Weekly Email Report",
    width="large",
)
def weekly_email_dialog(
    supabase,
    report_start,
    report_end,
    period_df,
    challenge_df,
    poi_df,
    fault_df,
    total_challenges,
    total_pois,
    total_faults,
    complete_challenges,
    needs_review_challenges,
    not_viewed_challenges,
    reversed_count,
    confirmed_count,
    stands_count,
    failure_count,
    reversal_rate,
    average_seconds,
):
    st.caption(
        f"{report_start:%B %d, %Y} through {report_end:%B %d, %Y}"
    )

    saved_recipients = load_saved_recipients(
        supabase
    )

    recipient_lookup = {
        str(recipient.get("id")): recipient
        for recipient in saved_recipients
        if recipient.get("id") is not None
    }

    period_conferences = sorted({
        clean_text(value)
        for value in period_df.get(
            "conference",
            pd.Series(dtype="object"),
        ).tolist()
        if clean_text(value)
    })

    default_ids = report_default_recipient_ids(
        saved_recipients,
        period_conferences,
    )

    selected_ids = st.multiselect(
        "Saved Recipients",
        options=list(recipient_lookup.keys()),
        default=[
            recipient_id
            for recipient_id in default_ids
            if recipient_id in recipient_lookup
        ],
        format_func=lambda recipient_id: recipient_label(
            recipient_lookup[recipient_id]
        ),
        key="weekly_email_saved_recipients",
    )

    manual_to = st.text_area(
        "Additional To Addresses",
        placeholder="name@example.com; second@example.com",
        height=70,
        key="weekly_email_manual_to",
    )

    cc_value = st.text_input(
        "Cc",
        key="weekly_email_cc",
    )

    bcc_value = st.text_input(
        "Bcc",
        key="weekly_email_bcc",
    )

    subject = st.text_input(
        "Subject",
        value=weekly_email_subject(
            report_start,
            report_end,
        ),
        key="weekly_email_subject",
    )

    custom_message = st.text_area(
        "Opening Message",
        placeholder=(
            "Optional note that will appear above the report."
        ),
        height=90,
        key="weekly_email_message",
    )

    option1, option2 = st.columns(2)

    with option1:
        include_challenge_details = st.checkbox(
            "Include challenge-by-challenge summary",
            value=True,
            key="weekly_email_include_challenges",
        )

    with option2:
        include_poi_fault_details = st.checkbox(
            "Include POI and Fault details",
            value=True,
            key="weekly_email_include_other_plays",
        )

    body = build_weekly_email_body(
        report_start=report_start,
        report_end=report_end,
        challenge_df=challenge_df,
        poi_df=poi_df,
        fault_df=fault_df,
        total_challenges=total_challenges,
        total_pois=total_pois,
        total_faults=total_faults,
        complete_challenges=complete_challenges,
        needs_review_challenges=needs_review_challenges,
        not_viewed_challenges=not_viewed_challenges,
        reversed_count=reversed_count,
        confirmed_count=confirmed_count,
        stands_count=stands_count,
        failure_count=failure_count,
        reversal_rate=reversal_rate,
        average_seconds=average_seconds,
        custom_message=custom_message,
        include_challenge_details=include_challenge_details,
        include_poi_fault_details=include_poi_fault_details,
    )

    selected_saved_addresses = [
        clean_text(
            recipient_lookup[recipient_id].get("email")
        )
        for recipient_id in selected_ids
        if recipient_id in recipient_lookup
    ]

    to_addresses = dedupe_addresses(
        selected_saved_addresses
        + split_manual_addresses(
            manual_to
        )
    )

    cc_addresses = dedupe_addresses(
        split_manual_addresses(
            cc_value
        )
    )

    bcc_addresses = dedupe_addresses(
        split_manual_addresses(
            bcc_value
        )
    )

    compose_url = gmail_compose_url(
        to_addresses,
        cc_addresses,
        bcc_addresses,
        subject,
        body,
    )

    st.text_area(
        "Email Preview",
        value=body,
        height=360,
        key="weekly_email_preview",
        disabled=True,
    )

    if not to_addresses:
        st.info(
            "No To recipient is selected yet. Gmail can still open, "
            "and you can add recipients there."
        )

    if len(compose_url) > 7500:
        st.warning(
            "This is a long report. Gmail URL composition can be less "
            "reliable with very large bodies. If Gmail truncates it, "
            "copy the Email Preview text into the draft."
        )

    st.link_button(
        "✉ Open Weekly Report in Gmail",
        compose_url,
        type="primary",
        use_container_width=True,
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

fault_df = period_df[
    period_df[
        "report_play_type"
    ]
    == "Fault"
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
total_faults = len(
    fault_df
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

k1, k2, k3, k4, k5, k6 = st.columns(
    6
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
        "Faults",
        f"{total_faults:,}",
        "Imported fault clips",
        "green",
    )

with k4:
    render_kpi(
        "Complete",
        f"{complete_challenges:,}",
        "Completed challenges",
        "green",
    )

with k5:
    render_kpi(
        "Needs Review",
        f"{needs_review_challenges:,}",
        "Challenges flagged",
        "purple",
    )

with k6:
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

reversed_count = 0
confirmed_count = 0
stands_count = 0
failure_count = 0
reversal_rate = 0.0
average_seconds = None

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
# FAULT SUMMARY
# ============================================================

if not fault_df.empty:
    render_section_label(
        "Faults"
    )

    fault_display = (
        fault_df[
            [
                "report_date",
                "conference",
                "match_name",
                "set_number",
                "score",
                "dvsport_play_category",
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

    fault_display.columns = [
        "Date",
        "Conference",
        "Match",
        "Set",
        "Score",
        "DV Sport Fault",
        "Review Status",
        "Coordinator Note",
    ]

    st.dataframe(
        fault_display,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# EMAIL REPORT
# ============================================================

render_section_label(
    "Email Report"
)

with st.container(
    border=True
):
    st.markdown(
        "**Generate a coordinator-ready email from this exact report window.**"
    )
    st.caption(
        "The email includes report inventory, challenge metrics, coordinator "
        "notes, and optional play-by-play details. Saved recipients from the "
        "challenge email system are available in the email dialog."
    )

    if st.button(
        "✉ Generate Email Report",
        type="primary",
        use_container_width=True,
        key="weekly_report_generate_email",
    ):
        weekly_email_dialog(
            supabase=supabase,
            report_start=report_start,
            report_end=report_end,
            period_df=period_df,
            challenge_df=challenge_df,
            poi_df=poi_df,
            fault_df=fault_df,
            total_challenges=total_challenges,
            total_pois=total_pois,
            total_faults=total_faults,
            complete_challenges=complete_challenges,
            needs_review_challenges=needs_review_challenges,
            not_viewed_challenges=not_viewed_challenges,
            reversed_count=reversed_count,
            confirmed_count=confirmed_count,
            stands_count=stands_count,
            failure_count=failure_count,
            reversal_rate=reversal_rate,
            average_seconds=average_seconds,
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
        f"{total_pois:,} POIs • "
        f"{total_faults:,} faults"
    )
)
