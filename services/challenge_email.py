from urllib.parse import urlencode

import streamlit as st

from services.challenge_download import (
    clean_text,
    clean_value,
    format_seconds,
)


# ============================================================
# RECIPIENTS
# ============================================================

def load_saved_recipients(
    supabase,
):
    try:
        response = (
            supabase
            .table("email_recipients")
            .select("*")
            .eq(
                "active",
                True,
            )
            .order(
                "name"
            )
            .execute()
        )

        return response.data or []

    except Exception:
        return []


def recipient_label(
    recipient,
):
    name = (
        clean_text(
            recipient.get(
                "name"
            )
        )
        or clean_text(
            recipient.get(
                "email"
            )
        )
        or "Recipient"
    )

    email = clean_text(
        recipient.get(
            "email"
        )
    )

    conference = clean_text(
        recipient.get(
            "conference"
        )
    )

    group_name = clean_text(
        recipient.get(
            "group_name"
        )
    )

    details = [
        item
        for item in [
            email,
            conference,
            group_name,
        ]
        if item
    ]

    if details:
        return (
            f"{name} — "
            + " • ".join(
                details
            )
        )

    return name


def default_recipient_ids(
    recipients,
    conference,
):
    conference_upper = (
        clean_text(
            conference
        )
        .upper()
    )

    defaults = []

    for recipient in recipients:
        if not recipient.get(
            "is_default"
        ):
            continue

        recipient_conference = (
            clean_text(
                recipient.get(
                    "conference"
                )
            )
            .upper()
        )

        if (
            not recipient_conference
            or recipient_conference
            in {
                "ALL",
                "NATIONAL",
            }
            or recipient_conference
            == conference_upper
        ):
            defaults.append(
                recipient.get(
                    "id"
                )
            )

    return [
        item
        for item in defaults
        if item is not None
    ]


def split_manual_addresses(
    value,
):
    raw = clean_text(
        value
    )

    if not raw:
        return []

    normalized = (
        raw
        .replace(
            ";",
            ",",
        )
        .replace(
            "\n",
            ",",
        )
    )

    return [
        item.strip()
        for item in normalized.split(
            ","
        )
        if item.strip()
    ]


def dedupe_addresses(
    values,
):
    result = []
    seen = set()

    for value in values:
        email = clean_text(
            value
        )

        if not email:
            continue

        key = email.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            email
        )

    return result


# ============================================================
# VIDEO LINKS
# ============================================================

def video_url_present(
    value,
):
    """
    Deliberately permissive.

    If DV Sport supplied a nonblank URL-like value, include it.
    We do NOT send an HTTP request, inspect MIME type, or try to
    pre-validate whether the media server will accept the request.
    """
    return bool(
        clean_text(
            value
        )
    )


def video_priority(
    angle,
):
    name = clean_text(
        angle.get(
            "angle_name"
        )
    ).upper()

    if "PGM" in name:
        return (
            0,
            name,
        )

    if (
        "REPLAY OUTPUT"
        in name
    ):
        return (
            1,
            name,
        )

    if "REPLAY" in name:
        return (
            2,
            name,
        )

    return (
        3,
        name,
    )


def ordered_video_links(
    video_angles,
):
    """
    Return every unique DV Sport video URL, ordered with the
    primary broadcast/replay angles first.
    """
    candidates = [
        angle
        for angle in (
            video_angles
            or []
        )
        if video_url_present(
            angle.get(
                "video_url"
            )
        )
    ]

    candidates = sorted(
        candidates,
        key=video_priority,
    )

    result = []
    seen_urls = set()

    for index, angle in enumerate(
        candidates,
        start=1,
    ):
        url = clean_text(
            angle.get(
                "video_url"
            )
        )

        if not url:
            continue

        key = url.strip()

        if key in seen_urls:
            continue

        seen_urls.add(
            key
        )

        angle_name = (
            clean_text(
                angle.get(
                    "angle_name"
                )
            )
            or f"Video {index}"
        )

        result.append(
            {
                "name":
                    angle_name,
                "url":
                    url,
            }
        )

    return result


# ============================================================
# EMAIL CONTENT
# ============================================================

def default_subject(
    play,
):
    match_name = (
        clean_text(
            play.get(
                "match_name"
            )
        )
        or "Match"
    )

    set_number = clean_text(
        play.get(
            "set_number"
        )
    )

    score = clean_text(
        play.get(
            "score"
        )
    )

    subject = (
        "Challenge Review"
        f" | {match_name}"
    )

    ending = []

    if set_number:
        ending.append(
            f"Set {set_number}"
        )

    if score:
        ending.append(
            score
        )

    if ending:
        subject += (
            " | "
            + " • ".join(
                ending
            )
        )

    return subject


def clean_line_value(
    value,
):
    text = clean_text(
        value
    )

    return (
        text
        if text
        else "—"
    )


def add_section(
    lines,
    title,
    items,
):
    useful_items = [
        (
            label,
            value,
        )
        for label, value
        in items
        if clean_text(
            value
        )
        and clean_text(
            value
        )
        != "—"
    ]

    if not useful_items:
        return

    lines.extend(
        [
            title.upper(),
            "─" * 42,
        ]
    )

    for label, value in useful_items:
        lines.append(
            (
                f"• {label}: "
                f"{value}"
            )
        )

    lines.append(
        ""
    )


def email_body(
    play,
    custom_message,
    include_basic,
    include_crs,
    include_result,
    include_length,
    include_review_tags,
    include_reviewer_notes,
    include_weekly_note,
    video_angles,
):
    """
    Gmail compose URLs accept plain text, not true HTML.

    This deliberately uses clean Unicode typography and compact
    sections so the resulting Gmail draft feels modern without
    displaying raw HTML tags.
    """
    lines = []

    match_name = clean_value(
        play.get(
            "match_name"
        ),
        "Challenge Review",
    )

    match_date = clean_text(
        play.get(
            "match_date"
        )
    )

    conference = clean_text(
        play.get(
            "conference"
        )
    )

    set_number = clean_text(
        play.get(
            "set_number"
        )
    )

    score = clean_text(
        play.get(
            "score"
        )
    )

    hero_meta = [
        item
        for item in [
            match_date,
            conference,
            (
                f"Set {set_number}"
                if set_number
                else ""
            ),
            (
                f"Score {score}"
                if score
                else ""
            ),
        ]
        if item
    ]

    lines.extend(
        [
            "NCAA WOMEN'S VOLLEYBALL • CHALLENGE REVIEW",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            match_name,
        ]
    )

    if hero_meta:
        lines.append(
            " • ".join(
                hero_meta
            )
        )

    lines.append(
        ""
    )

    if clean_text(
        custom_message
    ):
        lines.extend(
            [
                clean_text(
                    custom_message
                ),
                "",
                "──────────────────────────────────────────",
                "",
            ]
        )

    if include_basic:
        record_use = (
            "UNUSABLE — EXCLUDED FROM ANALYSIS / REPORTS"
            if play.get(
                "is_unusable"
            )
            is True
            else "Usable"
        )

        basic_items = [
            (
                "Challenging team",
                clean_line_value(
                    play.get(
                        "challenging_team"
                    )
                ),
            ),
            (
                "DV Sport challenge type",
                clean_line_value(
                    play.get(
                        "challenge_type"
                    )
                ),
            ),
            (
                "Record use",
                record_use,
            ),
        ]

        if (
            play.get(
                "is_unusable"
            )
            is True
        ):
            basic_items.append(
                (
                    "Unusable reason",
                    clean_line_value(
                        play.get(
                            "unusable_reason"
                        )
                    ),
                )
            )

            if clean_text(
                play.get(
                    "unusable_notes"
                )
            ):
                basic_items.append(
                    (
                        "Unusable details",
                        clean_text(
                            play.get(
                                "unusable_notes"
                            )
                        ),
                    )
                )

        add_section(
            lines,
            "Challenge",
            basic_items,
        )

    if include_crs:
        add_section(
            lines,
            "CRS Classification",
            [
                (
                    "DV Sport CRS category",
                    clean_line_value(
                        play.get(
                            "dvsport_crs_category"
                        )
                    ),
                ),
                (
                    "NCAA challenge category",
                    clean_line_value(
                        play.get(
                            "ncaa_challenge_category"
                        )
                        or play.get(
                            "crs_category"
                        )
                    ),
                ),
                (
                    "Original decision",
                    clean_line_value(
                        play.get(
                            "crs_original_decision"
                        )
                    ),
                ),
            ],
        )

    if include_result:
        add_section(
            lines,
            "Challenge Result",
            [
                (
                    "Outcome",
                    clean_line_value(
                        play.get("crs_outcome")
                        or play.get("challenge_result")
                    ),
                ),
                (
                    "Fault changed / new fault",
                    clean_line_value(
                        play.get("challenge_outcome_detail")
                    ),
                ),
            ],
        )

    if include_length:
        challenge_length = format_seconds(
            play.get(
                "challenge_length_seconds"
            )
        )

        if (
            challenge_length
            and challenge_length
            != "—"
        ):
            add_section(
                lines,
                "Review Timing",
                [
                    (
                        "Challenge length",
                        challenge_length,
                    ),
                ],
            )

    if include_review_tags:
        judgment = clean_text(play.get("referee_judgment"))
        if not judgment:
            legacy = play.get("review_decision_correct")
            judgment = (
                "Correct" if legacy is True
                else "Incorrect" if legacy is False
                else "Not tagged"
            )

        add_section(
            lines,
            "Review Tags",
            [
                ("Referee judgment", judgment),
                (
                    "Starred",
                    "Yes" if play.get("is_starred") is True else "No",
                ),
                (
                    "Review status",
                    clean_line_value(play.get("review_status") or "Not Viewed"),
                ),
            ],
        )

    if include_reviewer_notes:
        reviewer_notes = clean_text(
            play.get(
                "reviewer_notes"
            )
        )

        if reviewer_notes:
            lines.extend(
                [
                    "REVIEWER NOTES",
                    "─" * 42,
                    reviewer_notes,
                    "",
                ]
            )

    if include_weekly_note:
        weekly_note = clean_text(
            play.get(
                "weekly_summary_note"
            )
        )

        if weekly_note:
            lines.extend(
                [
                    "COORDINATOR NOTE",
                    "─" * 42,
                    weekly_note,
                    "",
                ]
            )

    # Video links are ALWAYS included.
    links = ordered_video_links(
        video_angles
    )

    lines.extend(
        [
            "VIDEO REPLAY LINKS",
            "─" * 42,
        ]
    )

    if links:
        for index, video in enumerate(
            links,
            start=1,
        ):
            lines.extend(
                [
                    (
                        f"{index:02d} • "
                        f"{video['name']}"
                    ),
                    video[
                        "url"
                    ],
                    "",
                ]
            )

    else:
        lines.extend(
            [
                "No video URLs are attached to this challenge.",
                "",
            ]
        )

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "NCAA Women's Volleyball Review",
        ]
    )

    return "\n".join(
        lines
    )


def gmail_compose_url(
    to_addresses,
    cc_addresses,
    bcc_addresses,
    subject,
    body,
):
    params = {
        "view":
            "cm",
        "fs":
            "1",
        "to":
            ", ".join(
                to_addresses
            ),
        "cc":
            ", ".join(
                cc_addresses
            ),
        "bcc":
            ", ".join(
                bcc_addresses
            ),
        "su":
            subject,
        "body":
            body,
    }

    return (
        "https://mail.google.com/mail/?"
        + urlencode(
            params
        )
    )


# ============================================================
# DIALOG
# ============================================================

@st.dialog(
    "Email Challenge",
    width="large",
)
def challenge_email_dialog(
    play,
    video_angles,
    supabase,
    key_prefix,
):
    st.markdown(
        (
            "### "
            f"{clean_value(play.get('match_name'), 'Challenge')}"
        )
    )

    summary_parts = [
        clean_text(
            play.get(
                "conference"
            )
        ),
        (
            f"Set "
            f"{clean_text(play.get('set_number'))}"
            if clean_text(
                play.get(
                    "set_number"
                )
            )
            else ""
        ),
        clean_text(
            play.get(
                "score"
            )
        ),
    ]

    st.caption(
        " • ".join(
            item
            for item in summary_parts
            if item
        )
    )

    video_links = ordered_video_links(
        video_angles
    )

    if video_links:
        st.success(
            (
                f"All {len(video_links):,} video "
                f"link{'' if len(video_links) == 1 else 's'} "
                "will be included automatically."
            ),
            icon="🔗",
        )
    else:
        st.warning(
            (
                "No video URLs are currently attached "
                "to this challenge."
            ),
            icon="⚠️",
        )

    # --------------------------------------------------------
    # RECIPIENTS
    # --------------------------------------------------------

    recipients = load_saved_recipients(
        supabase
    )

    recipient_map = {
        recipient.get(
            "id"
        ):
            recipient
        for recipient
        in recipients
        if recipient.get(
            "id"
        )
        is not None
    }

    default_ids = (
        default_recipient_ids(
            recipients,
            play.get(
                "conference"
            ),
        )
    )

    st.markdown(
        "#### Recipients"
    )

    if recipients:
        selected_ids = st.multiselect(
            "Saved Recipients",
            options=list(
                recipient_map.keys()
            ),
            default=[
                item
                for item
                in default_ids
                if item
                in recipient_map
            ],
            format_func=lambda item:
                recipient_label(
                    recipient_map[
                        item
                    ]
                ),
            key=(
                f"{key_prefix}_saved_"
                f"{play['id']}"
            ),
        )

    else:
        selected_ids = []

        st.info(
            (
                "No saved recipients are available yet. "
                "You can enter addresses manually."
            )
        )

    r1, r2, r3 = st.columns(
        3
    )

    with r1:
        manual_to = st.text_area(
            "Additional To",
            height=88,
            placeholder=(
                "name@example.com"
            ),
            key=(
                f"{key_prefix}_to_"
                f"{play['id']}"
            ),
        )

    with r2:
        manual_cc = st.text_area(
            "CC",
            height=88,
            placeholder="Optional",
            key=(
                f"{key_prefix}_cc_"
                f"{play['id']}"
            ),
        )

    with r3:
        manual_bcc = st.text_area(
            "BCC",
            height=88,
            placeholder="Optional",
            key=(
                f"{key_prefix}_bcc_"
                f"{play['id']}"
            ),
        )

    saved_to = [
        clean_text(
            recipient_map[
                item
            ].get(
                "email"
            )
        )
        for item in selected_ids
        if item
        in recipient_map
    ]

    to_addresses = dedupe_addresses(
        saved_to
        + split_manual_addresses(
            manual_to
        )
    )

    cc_addresses = dedupe_addresses(
        split_manual_addresses(
            manual_cc
        )
    )

    bcc_addresses = dedupe_addresses(
        split_manual_addresses(
            manual_bcc
        )
    )

    # --------------------------------------------------------
    # EMAIL
    # --------------------------------------------------------

    st.markdown(
        "#### Email"
    )

    subject = st.text_input(
        "Subject",
        value=default_subject(
            play
        ),
        key=(
            f"{key_prefix}_subject_"
            f"{play['id']}"
        ),
    )

    custom_message = st.text_area(
        "Message",
        placeholder=(
            "Optional note to place at the top of the email."
        ),
        height=95,
        key=(
            f"{key_prefix}_message_"
            f"{play['id']}"
        ),
    )

    st.markdown(
        "#### Include"
    )

    i1, i2 = st.columns(
        2
    )

    with i1:
        include_basic = st.checkbox(
            "Challenge information",
            value=True,
            key=(
                f"{key_prefix}_basic_"
                f"{play['id']}"
            ),
        )

        include_crs = st.checkbox(
            "CRS classification",
            value=True,
            key=(
                f"{key_prefix}_crs_"
                f"{play['id']}"
            ),
        )

        include_result = st.checkbox(
            "Challenge result",
            value=True,
            key=(
                f"{key_prefix}_result_"
                f"{play['id']}"
            ),
        )

        include_length = st.checkbox(
            "Challenge length",
            value=True,
            key=(
                f"{key_prefix}_length_"
                f"{play['id']}"
            ),
        )

    with i2:
        include_review_tags = st.checkbox(
            "Review tags",
            value=True,
            key=(
                f"{key_prefix}_review_tags_"
                f"{play['id']}"
            ),
        )

        include_reviewer_notes = False

        include_weekly_note = st.checkbox(
            "Coordinator note",
            value=False,
            key=(
                f"{key_prefix}_weekly_"
                f"{play['id']}"
            ),
        )

        st.checkbox(
            "All video replay links",
            value=True,
            disabled=True,
            key=(
                f"{key_prefix}_all_video_links_"
                f"{play['id']}"
            ),
            help=(
                "Every unique DV Sport video URL attached "
                "to this challenge is included automatically."
            ),
        )

    body = email_body(
        play=play,
        custom_message=custom_message,
        include_basic=include_basic,
        include_crs=include_crs,
        include_result=include_result,
        include_length=include_length,
        include_review_tags=(
            include_review_tags
        ),
        include_reviewer_notes=(
            include_reviewer_notes
        ),
        include_weekly_note=(
            include_weekly_note
        ),
        video_angles=video_angles,
    )

    with st.expander(
        "Preview Email",
        expanded=False,
    ):
        st.text_area(
            "Generated Message",
            value=body,
            height=420,
            disabled=True,
            label_visibility="collapsed",
        )

    gmail_url = gmail_compose_url(
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        body=body,
    )

    st.divider()

    action1, action2 = st.columns(
        [
            1.0,
            2.25,
        ]
    )

    with action1:
        if st.button(
            "Close",
            use_container_width=True,
            key=(
                f"{key_prefix}_close_"
                f"{play['id']}"
            ),
        ):
            st.rerun()

    with action2:
        st.link_button(
            "Open in Gmail →",
            gmail_url,
            use_container_width=True,
            type="primary",
            help=(
                "Opens Gmail with recipients, subject, "
                "review details, and every video link prefilled."
            ),
        )

    if not to_addresses:
        st.caption(
            (
                "No To recipient is selected yet. Gmail will "
                "still open and you can add the recipient there."
            )
        )


# ============================================================
# PAGE BUTTON
# ============================================================

def render_email_challenge_button(
    play,
    video_angles,
    supabase,
    key_prefix,
):
    if (
        clean_text(
            play.get(
                "play_type"
            )
        ).upper()
        not in {
            "CHALLENGE",
            "CHALLENGES",
        }
    ):
        return

    if st.button(
        "✉ Email Challenge",
        use_container_width=True,
        key=(
            f"{key_prefix}_email_challenge_"
            f"{play['id']}"
        ),
    ):
        challenge_email_dialog(
            play=play,
            video_angles=video_angles,
            supabase=supabase,
            key_prefix=key_prefix,
        )
