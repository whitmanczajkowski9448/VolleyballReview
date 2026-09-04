from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from services.auth import require_admin
from services.challenge_download import render_challenge_download
from services.challenge_email import render_email_challenge_button
from services.database import get_supabase
from services.play_media import video_angles_from_play
from services.review_taxonomy import (
    CHALLENGE_CATEGORIES,
    CHALLENGE_CATEGORY_LABELS,
    CHALLENGE_OUTCOMES,
    NEW_FAULT_OPTIONS,
    ORIGINAL_CALLS,
    REFEREE_JUDGMENTS,
    REVIEW_STATUS_CHOICES,
    normalize_challenge_category,
    normalize_original_call,
    normalize_outcome,
    normalize_referee_judgment,
    normalize_review_status,
)
from services.ui import (
    render_empty,
    render_page_header,
    render_section_label,
    render_status_pill,
)
from services.video_player import render_keyboard_video_workspace


require_admin()

render_page_header(
    "Tag / Edit",
    "Review each challenge, apply the coordinator tags, and move through the queue.",
    eyebrow="NCAA WVB • REVIEW WORKSPACE",
)

supabase = get_supabase()

scroll_to_main_video_after_render = bool(
    st.session_state.pop("editor_scroll_to_main_video", False)
)


def scroll_parent_to_main_video():
    components.html(
        """
        <script>
        (() => {
            try {
                const doc = window.parent.document;
                const anchor = doc.getElementById("editor-main-video-anchor");
                if (anchor) {
                    anchor.scrollIntoView({block: "start", behavior: "auto"});
                    return;
                }
                window.parent.scrollTo(0, 0);
            } catch (_) {}
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )


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


def clean_value(value, fallback="—"):
    return clean_text(value) or fallback


def normalized_play_type(value):
    text = clean_text(value).upper()
    if text in {"CHALLENGE", "CHALLENGES"}:
        return "Challenge"
    if text in {"POI", "POIS", "PLAY OF INTEREST", "PLAYS OF INTEREST"}:
        return "POI"
    if text in {"FAULT", "FAULTS"}:
        return "Fault"
    return clean_text(value) or "Unknown"


def date_value(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def parse_length(value):
    """Accept either seconds (84) or mm:ss (1:24), store integer seconds."""
    text = clean_text(value)
    if not text:
        return None
    if text.isdigit():
        return int(text)

    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes, seconds = [int(part) for part in parts]
    except ValueError:
        return None
    if minutes < 0 or seconds < 0 or seconds >= 60:
        return None
    return minutes * 60 + seconds


def seconds_to_time(value):
    try:
        total = int(value)
    except (TypeError, ValueError):
        return ""
    return f"{total // 60}:{total % 60:02d}"


def initialize(key, value):
    if key not in st.session_state:
        st.session_state[key] = value


def challenge_length_value(play):
    value = play.get("challenge_length_seconds")
    if value is None:
        value = play.get("dvsport_challenge_length_seconds")
    return value


def queue_match_key(item):
    return (
        clean_text(item.get("match_date")),
        clean_text(item.get("conference")),
        clean_text(item.get("match_name")),
    )


def queue_match_label(key, count):
    date_text, conference, match = key
    return (
        f"{date_text or 'No Date'} • {conference or 'No Conference'} • "
        f"{match or 'Unnamed Match'} ({count})"
    )


def queue_play_label(item, position, total):
    parts = [f"{item['_queue_play_type'].upper()} {position}/{total}"]
    if clean_text(item.get("set_number")):
        parts.append(f"Set {item.get('set_number')}")
    if clean_text(item.get("score")):
        parts.append(clean_text(item.get("score")))
    if item["_queue_play_type"] == "Challenge":
        category = item.get("_queue_category") or "Unclassified"
        parts.append(category)
        parts.append(item.get("_queue_outcome") or "Not Tagged")
    parts.append(item["_queue_status"])
    return " • ".join(parts)


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
    plays = response.data or []
except Exception as exc:
    st.error("Could not load plays.")
    st.exception(exc)
    st.stop()

if not plays:
    render_empty("No plays are available yet.")
    st.stop()

for item in plays:
    item["_queue_play_type"] = normalized_play_type(item.get("play_type"))
    item["_queue_status"] = normalize_review_status(item.get("review_status"))
    item["_queue_date"] = date_value(item.get("match_date"))
    item["_queue_category"] = normalize_challenge_category(
        item.get("ncaa_challenge_category") or item.get("crs_category")
    )
    item["_queue_outcome"] = normalize_outcome(
        item.get("crs_outcome") or item.get("challenge_result")
    )
    item["_queue_judgment"] = normalize_referee_judgment(
        item.get("referee_judgment"),
        item.get("review_decision_correct"),
    ) or "Not Tagged"

# Legacy unusable rows stay out of the working queue, but the old field is no
# longer part of the tagging workflow.
plays = [item for item in plays if item.get("is_unusable") is not True]


# ============================================================
# FILTERS
# ============================================================

render_section_label("Choose a Play")

conferences = sorted({
    clean_text(item.get("conference"))
    for item in plays
    if clean_text(item.get("conference"))
})
outcomes = sorted({
    item["_queue_outcome"]
    for item in plays
    if item["_queue_play_type"] == "Challenge" and item["_queue_outcome"]
})
valid_dates = [item["_queue_date"] for item in plays if item["_queue_date"] is not None]
min_date = min(valid_dates) if valid_dates else date.today()
max_date = max(valid_dates) if valid_dates else date.today()

with st.expander("Filters", expanded=False):
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        play_type_filter = st.selectbox(
            "Play Type",
            ["Challenge", "All", "POI", "Fault"],
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
            ["All", "Not Viewed", "Needs Additional Review", "Complete"],
            key="editor_filter_status",
        )
    with f4:
        judgment_filter = st.selectbox(
            "Referee Judgment",
            ["All", "Correct", "Incorrect", "Unclear", "Not Tagged"],
            key="editor_filter_judgment",
        )

    d1, d2, d3 = st.columns([1, 1, 1])
    with d1:
        date_mode = st.selectbox(
            "Date Range",
            ["All Dates", "Last 7 Days", "Custom"],
            key="editor_filter_date_mode",
        )

    filter_start = None
    filter_end = None
    if date_mode == "Last 7 Days":
        filter_end = date.today()
        filter_start = filter_end - timedelta(days=6)
    elif date_mode == "Custom":
        with d2:
            filter_start = st.date_input(
                "Start Date",
                value=min_date,
                key="editor_filter_start_date",
            )
        with d3:
            filter_end = st.date_input(
                "End Date",
                value=max_date,
                key="editor_filter_end_date",
            )
        if filter_start > filter_end:
            st.error("Start Date cannot be after End Date.")
            st.stop()

    c1, c2 = st.columns(2)
    with c1:
        outcome_filter = st.selectbox(
            "Challenge Outcome",
            ["All"] + outcomes,
            key="editor_filter_outcome",
        )
    with c2:
        search_filter = st.text_input(
            "Search",
            placeholder="Match, team, score, category, note...",
            key="editor_filter_search",
        )

    if st.button("Reset Filters", key="editor_reset_filters"):
        for state_key in list(st.session_state.keys()):
            if state_key.startswith("editor_filter_"):
                st.session_state.pop(state_key, None)
        st.session_state.pop("editor_match_picker", None)
        st.session_state.pop("editor_play_picker", None)
        st.rerun()


filtered_plays = []
search_term = clean_text(search_filter).lower()

for item in plays:
    if play_type_filter != "All" and item["_queue_play_type"] != play_type_filter:
        continue
    if conference_filter != "All" and clean_text(item.get("conference")) != conference_filter:
        continue
    if status_filter != "All" and item["_queue_status"] != status_filter:
        continue
    if judgment_filter != "All" and item["_queue_judgment"] != judgment_filter:
        continue
    if filter_start is not None and (item["_queue_date"] is None or item["_queue_date"] < filter_start):
        continue
    if filter_end is not None and (item["_queue_date"] is None or item["_queue_date"] > filter_end):
        continue
    if outcome_filter != "All":
        if item["_queue_play_type"] != "Challenge" or item["_queue_outcome"] != outcome_filter:
            continue
    if search_term:
        haystack = " ".join([
            clean_text(item.get("match_name")),
            clean_text(item.get("conference")),
            clean_text(item.get("score")),
            clean_text(item.get("challenging_team")),
            clean_text(item.get("dvsport_crs_category")),
            clean_text(item.get("challenge_result")),
            clean_text(item.get("ncaa_challenge_category")),
            clean_text(item.get("crs_original_decision")),
            clean_text(item.get("crs_outcome")),
            clean_text(item.get("challenge_outcome_detail")),
            clean_text(item.get("referee_judgment")),
            clean_text(item.get("weekly_summary_note")),
        ]).lower()
        if search_term not in haystack:
            continue
    filtered_plays.append(item)

if not filtered_plays:
    render_empty("No plays match the current filters.")
    st.stop()


# ============================================================
# MATCH / PLAY BROWSER
# ============================================================

match_to_plays = {}
match_keys = []
for item in filtered_plays:
    key = queue_match_key(item)
    if key not in match_to_plays:
        match_to_plays[key] = []
        match_keys.append(key)
    match_to_plays[key].append(item)

match_picker_key = "editor_match_picker"
play_picker_key = "editor_play_picker"

pending_id = st.session_state.pop("editor_pending_play_id", None)
if pending_id is not None:
    target = next((item for item in filtered_plays if item.get("id") == pending_id), None)
    if target is not None:
        st.session_state[match_picker_key] = queue_match_key(target)
        st.session_state[play_picker_key] = pending_id

if st.session_state.get(match_picker_key) not in match_keys:
    st.session_state[match_picker_key] = match_keys[0]

browse1, browse2 = st.columns([1.15, 1.45])
with browse1:
    selected_match_key = st.selectbox(
        "Match",
        match_keys,
        key=match_picker_key,
        format_func=lambda key: queue_match_label(key, len(match_to_plays[key])),
    )

current_match_plays = match_to_plays[selected_match_key]
current_match_ids = [item["id"] for item in current_match_plays]
if st.session_state.get(play_picker_key) not in current_match_ids:
    st.session_state[play_picker_key] = current_match_ids[0]

play_by_id = {item["id"]: item for item in current_match_plays}
play_position = {item["id"]: index + 1 for index, item in enumerate(current_match_plays)}

with browse2:
    selected_play_id = st.selectbox(
        "Challenge / Play",
        current_match_ids,
        key=play_picker_key,
        format_func=lambda play_id: queue_play_label(
            play_by_id[play_id],
            play_position[play_id],
            len(current_match_ids),
        ),
    )

play = play_by_id[selected_play_id]
play_id = play["id"]
is_challenge = play["_queue_play_type"] == "Challenge"

queue_ids = [item["id"] for item in filtered_plays]
queue_index = queue_ids.index(play_id)
next_play_id = queue_ids[queue_index + 1] if queue_index + 1 < len(queue_ids) else None
filtered_play_by_id = {item["id"]: item for item in filtered_plays}

st.caption(f"{len(filtered_plays):,} plays • {len(match_keys):,} matches")


# ============================================================
# PLAY HEADER + ACTIONS
# ============================================================

st.divider()
title_col, status_col = st.columns([5, 1.2])
with title_col:
    st.subheader(clean_value(play.get("match_name"), "Play"))
with status_col:
    render_status_pill(play["_queue_status"])

info1, info2, info3, info4 = st.columns(4)
with info1:
    st.caption("CONFERENCE")
    st.write(clean_value(play.get("conference")))
with info2:
    st.caption("DATE")
    st.write(clean_value(play.get("match_date")))
with info3:
    st.caption("SET")
    st.write(clean_value(play.get("set_number")))
with info4:
    st.caption("SCORE")
    st.write(clean_value(play.get("score")))

angles = video_angles_from_play(play)
if is_challenge:
    a1, a2, a3 = st.columns([1.25, 1.25, 2.5])
    with a1:
        render_challenge_download(play, angles, "editor")
    with a2:
        render_email_challenge_button(play, angles, supabase, "editor")


# ============================================================
# VIDEO
# ============================================================

st.markdown('<div id="editor-main-video-anchor"></div>', unsafe_allow_html=True)
if scroll_to_main_video_after_render:
    scroll_parent_to_main_video()

render_section_label("Play Video")
if angles:
    player_angles = [dict(angle) for angle in angles]
    player_angles[0]["_volleyreview_meta"] = {
        "challenge_category": (
            clean_text(play.get("dvsport_crs_category"))
            or clean_text(play.get("challenge_type"))
        ),
        "challenge_result": clean_text(play.get("challenge_result")),
        "set_number": clean_text(play.get("set_number")),
        "score": clean_text(play.get("score")),
    }
    render_keyboard_video_workspace(
        player_angles,
        key=f"editor_play_{play_id}",
    )
else:
    render_empty("No video is attached to this play.")


# ============================================================
# STREAMLINED TAGGING
# ============================================================

save_message_key = f"save_message_{play_id}"
if st.session_state.get(save_message_key):
    st.success(st.session_state[save_message_key])

category_key = f"category_{play_id}"
original_key = f"original_{play_id}"
outcome_key = f"outcome_{play_id}"
detail_key = f"outcome_detail_{play_id}"
length_key = f"length_{play_id}"
judgment_key = f"judgment_{play_id}"
star_key = f"star_{play_id}"
weekly_key = f"weekly_{play_id}"
status_key = f"status_{play_id}"

stored_category = normalize_challenge_category(
    play.get("ncaa_challenge_category") or play.get("crs_category")
)
initialize(category_key, stored_category)

if is_challenge:
    render_section_label("Challenge Review")
    st.caption("Choose the Challenge Category first; the remaining tags save together.")
    category = st.selectbox(
        "Challenge Category",
        CHALLENGE_CATEGORIES,
        key=category_key,
        format_func=lambda value: CHALLENGE_CATEGORY_LABELS.get(value, value or "— Select —"),
    )
else:
    category = ""

stored_original = normalize_original_call(play.get("crs_original_decision"))
original_options = [""] + list(ORIGINAL_CALLS.get(category, []))
if stored_original and stored_original not in original_options:
    original_options.append(stored_original)
initialize(original_key, stored_original if stored_original in original_options else "")
if st.session_state.get(original_key) not in original_options:
    st.session_state[original_key] = ""

stored_outcome = normalize_outcome(play.get("crs_outcome") or play.get("challenge_result"))
initialize(outcome_key, stored_outcome if stored_outcome in CHALLENGE_OUTCOMES else "")
if st.session_state.get(outcome_key) not in CHALLENGE_OUTCOMES:
    st.session_state[outcome_key] = ""

stored_detail = clean_text(play.get("challenge_outcome_detail"))
if not stored_detail and play.get("crs_original_fault_changed") is not None:
    stored_detail = "Yes" if play.get("crs_original_fault_changed") is True else "No"
if not stored_detail and stored_outcome in {"Confirmed", "Stands"}:
    stored_detail = "No"
detail_options = [""] + ["No", "Yes"] + [x for x in NEW_FAULT_OPTIONS if x not in {"No", "Yes"}]
if stored_detail and stored_detail not in detail_options:
    detail_options.append(stored_detail)
initialize(detail_key, stored_detail)

stored_judgment = normalize_referee_judgment(
    play.get("referee_judgment"),
    play.get("review_decision_correct"),
)
initialize(judgment_key, stored_judgment if stored_judgment in REFEREE_JUDGMENTS else "")

initialize(length_key, seconds_to_time(challenge_length_value(play)))
initialize(star_key, bool(play.get("is_starred")))
initialize(weekly_key, clean_text(play.get("weekly_summary_note")))

stored_status = normalize_review_status(play.get("review_status"))
status_seed = "" if stored_status == "Not Viewed" else stored_status
initialize(status_key, status_seed if status_seed in REVIEW_STATUS_CHOICES else "")

with st.form(
    key=f"review_form_{play_id}",
    clear_on_submit=False,
    border=False,
):
    if is_challenge:
        row1, row2 = st.columns(2)
        with row1:
            original_call = st.selectbox(
                "Original Call",
                original_options,
                key=original_key,
                format_func=lambda value: value or "— Select —",
            )
        with row2:
            outcome = st.selectbox(
                "Challenge Outcome",
                CHALLENGE_OUTCOMES,
                key=outcome_key,
                format_func=lambda value: value or "— Select —",
            )

        row3, row4 = st.columns(2)
        with row3:
            outcome_detail = st.selectbox(
                "Fault Changed / New Fault",
                detail_options,
                key=detail_key,
                format_func=lambda value: value or "— Select —",
                help=(
                    "Confirmed/Stands: choose No or Yes for whether the original fault changed. "
                    "Reversed: choose the new fault."
                ),
            )
        with row4:
            challenge_length = st.text_input(
                "Challenge Length (mm:ss)",
                key=length_key,
                placeholder="1:24",
                help="You may also enter total seconds, such as 84.",
            )

        judgment = st.selectbox(
            "Referee Judgment",
            REFEREE_JUDGMENTS,
            key=judgment_key,
            format_func=lambda value: value or "— Select —",
        )
    else:
        original_call = clean_text(play.get("crs_original_decision"))
        outcome = normalize_outcome(play.get("crs_outcome") or play.get("challenge_result"))
        outcome_detail = clean_text(play.get("challenge_outcome_detail"))
        challenge_length = seconds_to_time(challenge_length_value(play))
        judgment = normalize_referee_judgment(
            play.get("referee_judgment"), play.get("review_decision_correct")
        )

    st.divider()
    star_col, status_col = st.columns([1, 2])
    with star_col:
        is_starred = st.checkbox("★ Star", key=star_key)
    with status_col:
        review_status_choice = st.selectbox(
            "Review Status",
            REVIEW_STATUS_CHOICES,
            key=status_key,
            format_func=lambda value: "Not Viewed (unmarked)" if not value else value,
        )

    weekly_summary_note = st.text_area(
        "Weekly Summary Note",
        key=weekly_key,
        height=110,
        placeholder="Only add a note when this challenge needs coordinator attention.",
    )

    b1, b2 = st.columns([1, 1.25])
    with b1:
        save_clicked = st.form_submit_button(
            "Save Review",
            use_container_width=True,
        )
    with b2:
        save_next_clicked = st.form_submit_button(
            "Save & Next →",
            type="primary",
            use_container_width=True,
            disabled=next_play_id is None,
        )


def save_current_review():
    length_seconds = parse_length(challenge_length)
    if clean_text(challenge_length) and length_seconds is None:
        st.error("Challenge Length must be mm:ss (for example 1:24) or total seconds.")
        return False

    # Preserve the existing database status value for compatibility while the UI
    # uses the clearer "Needs Additional Review" label.
    status_to_save = (
        "Needs Review"
        if review_status_choice == "Needs Additional Review"
        else (review_status_choice or "Not Viewed")
    )

    if is_challenge:
        valid_calls = ORIGINAL_CALLS.get(category, [])
        if original_call and original_call not in valid_calls:
            st.error("The Original Call does not match the selected Challenge Category.")
            return False

        if status_to_save == "Complete":
            missing = []
            if not category:
                missing.append("Challenge Category")
            if not original_call:
                missing.append("Original Call")
            if not outcome:
                missing.append("Challenge Outcome")
            if not judgment:
                missing.append("Referee Judgment")
            if missing:
                st.error("Complete challenges require: " + ", ".join(missing) + ".")
                return False

        detail_to_save = clean_text(outcome_detail)
        changed_to_save = None

        if outcome in {"Confirmed", "Stands"}:
            if not detail_to_save:
                detail_to_save = "No"
            if detail_to_save not in {"No", "Yes"}:
                st.error("For Confirmed or Stands, Fault Changed / New Fault must be No or Yes.")
                return False
            changed_to_save = detail_to_save == "Yes"

        elif outcome == "Reversed":
            if not detail_to_save or detail_to_save in {"No", "Yes"}:
                st.error("For a Reversed challenge, choose the new fault in Fault Changed / New Fault.")
                return False

        elif outcome == "Mechanical Failure":
            detail_to_save = None

        if judgment == "Correct":
            legacy_accuracy = True
        elif judgment == "Incorrect":
            legacy_accuracy = False
        else:
            legacy_accuracy = None

        update_data = {
            "ncaa_challenge_category": category or None,
            "crs_original_decision": original_call or None,
            "crs_outcome": outcome or None,
            "challenge_outcome_detail": detail_to_save or None,
            "crs_original_fault_changed": changed_to_save,
            "challenge_length_seconds": length_seconds,
            "referee_judgment": judgment or None,
            "review_decision_correct": legacy_accuracy,
            "is_starred": bool(is_starred),
            "weekly_summary_note": clean_text(weekly_summary_note) or None,
            "review_status": status_to_save,
        }
    else:
        update_data = {
            "is_starred": bool(is_starred),
            "weekly_summary_note": clean_text(weekly_summary_note) or None,
            "review_status": status_to_save,
        }

    try:
        (
            supabase.table("plays")
            .update(update_data)
            .eq("id", play_id)
            .execute()
        )
        st.session_state[save_message_key] = (
            "✓ Saved " + datetime.now().strftime("%I:%M:%S %p")
        )
        return True
    except Exception as exc:
        st.error("The review could not be saved.")
        st.exception(exc)
        return False


def move_to_play(target_play_id):
    if target_play_id is None or target_play_id not in filtered_play_by_id:
        return
    st.session_state["editor_pending_play_id"] = target_play_id
    st.session_state["editor_scroll_to_main_video"] = True


if save_clicked:
    if save_current_review():
        st.rerun()

if save_next_clicked:
    if save_current_review():
        move_to_play(next_play_id)
        st.rerun()
