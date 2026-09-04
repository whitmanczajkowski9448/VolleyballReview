from datetime import date, timedelta

import pandas as pd
import streamlit as st

from services.auth import is_admin
from services.challenge_download import render_challenge_download
from services.challenge_email import render_email_challenge_button
from services.database import get_supabase
from services.play_media import video_angles_from_play
from services.review_taxonomy import (
    normalize_challenge_category,
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


render_page_header(
    "Play Library",
    "Search, filter, and review DV Sport media without changing review data.",
    eyebrow="NCAA WVB • REVIEW LIBRARY",
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


def format_seconds(value):
    try:
        total = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"{total // 60}:{total % 60:02d}"


def challenge_length_value(play):
    value = play.get("challenge_length_seconds")
    return value if value is not None else play.get("dvsport_challenge_length_seconds")


def match_key(item):
    return (
        clean_text(item.get("match_date")),
        clean_text(item.get("conference")),
        clean_text(item.get("match_name")),
    )


def match_label(key, count):
    d, c, m = key
    return f"{d or 'No Date'} • {c or 'No Conference'} • {m or 'Unnamed Match'} ({count})"


def play_label(item, position, total):
    parts = [f"{item['_type'].upper()} {position}/{total}"]
    if clean_text(item.get("set_number")):
        parts.append(f"Set {item.get('set_number')}")
    if clean_text(item.get("score")):
        parts.append(clean_text(item.get("score")))
    if item["_type"] == "Challenge":
        parts.append(item["_category"] or "Unclassified")
        parts.append(item["_outcome"] or "Not Tagged")
    parts.append(item["_status"])
    return " • ".join(parts)


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

plays = [item for item in plays if item.get("is_unusable") is not True]
for item in plays:
    item["_type"] = normalized_play_type(item.get("play_type"))
    item["_status"] = normalize_review_status(item.get("review_status"))
    item["_date"] = date_value(item.get("match_date"))
    item["_category"] = normalize_challenge_category(
        item.get("ncaa_challenge_category") or item.get("crs_category")
    )
    item["_outcome"] = normalize_outcome(item.get("crs_outcome") or item.get("challenge_result"))
    item["_judgment"] = normalize_referee_judgment(
        item.get("referee_judgment"), item.get("review_decision_correct")
    ) or "Not Tagged"

conferences = sorted({clean_text(item.get("conference")) for item in plays if clean_text(item.get("conference"))})
categories = sorted({item["_category"] for item in plays if item["_type"] == "Challenge" and item["_category"]})
outcomes = sorted({item["_outcome"] for item in plays if item["_type"] == "Challenge" and item["_outcome"]})
valid_dates = [item["_date"] for item in plays if item["_date"] is not None]
min_date = min(valid_dates) if valid_dates else date.today()
max_date = max(valid_dates) if valid_dates else date.today()

with st.expander("Filters", expanded=False):
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        type_filter = st.selectbox("Play Type", ["All", "Challenge", "POI", "Fault"], key="viewer_type")
    with f2:
        conf_filter = st.selectbox("Conference", ["All"] + conferences, key="viewer_conf")
    with f3:
        status_filter = st.selectbox(
            "Review Status",
            ["All", "Not Viewed", "Needs Additional Review", "Complete"],
            key="viewer_status",
        )
    with f4:
        judgment_filter = st.selectbox(
            "Referee Judgment",
            ["All", "Correct", "Incorrect", "Unclear", "Not Tagged"],
            key="viewer_judgment",
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        category_filter = st.selectbox("Challenge Category", ["All"] + categories, key="viewer_category")
    with c2:
        outcome_filter = st.selectbox("Challenge Outcome", ["All"] + outcomes, key="viewer_outcome")
    with c3:
        star_filter = st.selectbox("Starred", ["All", "Starred", "Not Starred"], key="viewer_star")

    d1, d2, d3 = st.columns(3)
    with d1:
        date_mode = st.selectbox("Date Range", ["All Dates", "Last 7 Days", "Custom"], key="viewer_date_mode")
    filter_start = None
    filter_end = None
    if date_mode == "Last 7 Days":
        filter_end = date.today()
        filter_start = filter_end - timedelta(days=6)
    elif date_mode == "Custom":
        with d2:
            filter_start = st.date_input("Start Date", value=min_date, key="viewer_start")
        with d3:
            filter_end = st.date_input("End Date", value=max_date, key="viewer_end")
        if filter_start > filter_end:
            st.error("Start Date cannot be after End Date.")
            st.stop()

    search = st.text_input(
        "Search",
        placeholder="Match, team, score, category, note...",
        key="viewer_search",
    )

filtered = []
term = clean_text(search).lower()
for item in plays:
    if type_filter != "All" and item["_type"] != type_filter:
        continue
    if conf_filter != "All" and clean_text(item.get("conference")) != conf_filter:
        continue
    if status_filter != "All" and item["_status"] != status_filter:
        continue
    if judgment_filter != "All" and item["_judgment"] != judgment_filter:
        continue
    if category_filter != "All" and (item["_type"] != "Challenge" or item["_category"] != category_filter):
        continue
    if outcome_filter != "All" and (item["_type"] != "Challenge" or item["_outcome"] != outcome_filter):
        continue
    if star_filter == "Starred" and item.get("is_starred") is not True:
        continue
    if star_filter == "Not Starred" and item.get("is_starred") is True:
        continue
    if filter_start is not None and (item["_date"] is None or item["_date"] < filter_start):
        continue
    if filter_end is not None and (item["_date"] is None or item["_date"] > filter_end):
        continue
    if term:
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
        if term not in haystack:
            continue
    filtered.append(item)

if not filtered:
    render_empty("No plays match the current filters.")
    st.stop()

match_to_plays = {}
match_keys = []
for item in filtered:
    key = match_key(item)
    if key not in match_to_plays:
        match_to_plays[key] = []
        match_keys.append(key)
    match_to_plays[key].append(item)

if st.session_state.get("viewer_match") not in match_keys:
    st.session_state["viewer_match"] = match_keys[0]

b1, b2 = st.columns([1.15, 1.45])
with b1:
    selected_match = st.selectbox(
        "Match",
        match_keys,
        key="viewer_match",
        format_func=lambda key: match_label(key, len(match_to_plays[key])),
    )

current = match_to_plays[selected_match]
ids = [item["id"] for item in current]
if st.session_state.get("viewer_play") not in ids:
    st.session_state["viewer_play"] = ids[0]
by_id = {item["id"]: item for item in current}
pos = {item["id"]: i + 1 for i, item in enumerate(current)}

with b2:
    selected_id = st.selectbox(
        "Challenge / Play",
        ids,
        key="viewer_play",
        format_func=lambda pid: play_label(by_id[pid], pos[pid], len(ids)),
    )

play = by_id[selected_id]
play_type = play["_type"]
is_challenge = play_type == "Challenge"

st.caption(f"{len(filtered):,} plays • {len(match_keys):,} matches")
st.divider()

header1, header2 = st.columns([5, 1.2])
with header1:
    st.subheader(clean_value(play.get("match_name"), "Play"))
with header2:
    render_status_pill(play["_status"])

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.caption("CONFERENCE")
    st.write(clean_value(play.get("conference")))
with m2:
    st.caption("DATE")
    st.write(clean_value(play.get("match_date")))
with m3:
    st.caption("SET")
    st.write(clean_value(play.get("set_number")))
with m4:
    st.caption("SCORE")
    st.write(clean_value(play.get("score")))

angles = video_angles_from_play(play)
if is_challenge:
    a1, a2, a3 = st.columns([1.25, 1.25, 2.5])
    with a1:
        render_challenge_download(play, angles, "viewer")
    with a2:
        if is_admin():
            render_email_challenge_button(play, angles, supabase, "viewer")

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
        key=f"viewer_play_{selected_id}",
    )
else:
    render_empty("No video is attached to this play.")

if is_challenge:
    render_section_label("Challenge Review")
    r1, r2, r3 = st.columns(3)
    with r1:
        st.caption("CHALLENGE CATEGORY")
        st.subheader(play["_category"] or "—")
        st.caption("ORIGINAL CALL")
        st.write(clean_value(play.get("crs_original_decision")))
    with r2:
        st.caption("OUTCOME")
        st.subheader(play["_outcome"] or "—")
        st.caption("FAULT CHANGED / NEW FAULT")
        st.write(clean_value(play.get("challenge_outcome_detail")))
    with r3:
        st.caption("REFEREE JUDGMENT")
        st.subheader(play["_judgment"] if play["_judgment"] != "Not Tagged" else "—")
        st.caption("CHALLENGE LENGTH")
        st.write(format_seconds(challenge_length_value(play)))

    if play.get("is_starred") is True:
        st.success("★ Starred")

note = clean_text(play.get("weekly_summary_note"))
if note:
    render_section_label("Weekly Summary Note")
    st.info(note)
