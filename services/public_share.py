import base64
import hashlib
import hmac
from urllib.parse import quote, urlsplit, urlunsplit

import streamlit as st
from supabase import create_client

from services.play_media import video_angles_from_play
from services.review_taxonomy import (
    normalize_challenge_category,
    normalize_outcome,
    normalize_referee_judgment,
    normalize_review_status,
)
from services.ui import render_page_header, render_section_label, render_status_pill
from services.video_player import render_keyboard_video_workspace


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _share_secret():
    configured = clean_text(st.secrets.get("PUBLIC_SHARE_SECRET", ""))
    if configured:
        return configured.encode("utf-8")

    service_key = clean_text(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    if not service_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is required for signed public challenge links."
        )
    return service_key.encode("utf-8")


def make_public_challenge_token(play_id):
    payload = clean_text(play_id)
    if not payload:
        return ""

    signature = hmac.new(
        _share_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    raw = f"v1:{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_public_challenge_token(token):
    token = clean_text(token)
    if not token:
        return None

    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + padding).decode("utf-8")
        version, payload, signature = raw.split(":", 2)
    except Exception:
        return None

    if version != "v1" or not payload or not signature:
        return None

    expected = hmac.new(
        _share_secret(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    if not hmac.compare_digest(signature, expected):
        return None

    return payload


def app_base_url():
    configured = clean_text(st.secrets.get("PUBLIC_APP_URL", ""))
    if configured:
        return configured.rstrip("/")

    try:
        raw_url = clean_text(st.context.url)
    except Exception:
        raw_url = ""

    if raw_url:
        parts = urlsplit(raw_url)
        if parts.scheme and parts.netloc:
            return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")

    try:
        headers = st.context.headers
        host = clean_text(
            headers.get("X-Forwarded-Host")
            or headers.get("Host")
        )
        proto = clean_text(headers.get("X-Forwarded-Proto")) or "https"
        if host:
            return f"{proto}://{host}".rstrip("/")
    except Exception:
        pass

    return ""


def public_challenge_url(play_id):
    token = make_public_challenge_token(play_id)
    if not token:
        return ""
    base = app_base_url()
    suffix = f"?challenge={quote(token)}"
    return f"{base}{suffix}" if base else suffix


def _public_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"],
    )


def fetch_public_challenge(token):
    play_id = decode_public_challenge_token(token)
    if not play_id:
        return None

    response = (
        _public_supabase()
        .table("plays")
        .select("*")
        .eq("id", play_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None

    play = rows[0]
    if clean_text(play.get("play_type")).upper() not in {"CHALLENGE", "CHALLENGES"}:
        return None
    return play


def format_seconds(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def render_public_challenge(token):
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        play = fetch_public_challenge(token)
    except Exception:
        play = None

    if not play:
        render_page_header(
            "Challenge Not Available",
            "This shared challenge link is invalid or no longer available.",
            eyebrow="NCAA WVB • SHARED REVIEW",
        )
        return

    render_page_header(
        clean_text(play.get("match_name")) or "Challenge Review",
        "Read-only shared challenge review.",
        eyebrow="NCAA WVB • SHARED CHALLENGE",
    )

    meta1, meta2, meta3, meta4 = st.columns(4)
    with meta1:
        st.metric("Conference", clean_text(play.get("conference")) or "—")
    with meta2:
        st.metric("Date", clean_text(play.get("match_date")) or "—")
    with meta3:
        st.metric("Set", clean_text(play.get("set_number")) or "—")
    with meta4:
        st.metric("Score", clean_text(play.get("score")) or "—")

    angles = video_angles_from_play(play)
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
            key=f"public_challenge_{play.get('id', 'shared')}",
        )
    else:
        st.warning("No video is available for this shared challenge.")

    render_section_label("Review Summary")
    category = normalize_challenge_category(
        play.get("ncaa_challenge_category") or play.get("crs_category")
    )
    outcome = normalize_outcome(
        play.get("crs_outcome") or play.get("challenge_result")
    )
    judgment = normalize_referee_judgment(
        play.get("referee_judgment"),
        play.get("review_decision_correct"),
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("CHALLENGE CATEGORY")
        st.subheader(category or "—")
        st.caption("ORIGINAL CALL")
        st.write(clean_text(play.get("crs_original_decision")) or "—")
    with c2:
        st.caption("OUTCOME")
        st.subheader(outcome or "—")
        st.caption("FAULT CHANGED / NEW FAULT")
        st.write(clean_text(play.get("challenge_outcome_detail")) or "—")
    with c3:
        st.caption("REFEREE JUDGMENT")
        st.subheader(judgment or "—")
        st.caption("CHALLENGE LENGTH")
        st.write(format_seconds(
            play.get("challenge_length_seconds")
            if play.get("challenge_length_seconds") is not None
            else play.get("dvsport_challenge_length_seconds")
        ))

    render_status_pill(normalize_review_status(play.get("review_status")))

    note = clean_text(play.get("weekly_summary_note"))
    if note:
        render_section_label("Coordinator Note")
        st.info(note)
