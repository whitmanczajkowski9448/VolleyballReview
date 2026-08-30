from urllib.parse import urlencode

import streamlit as st

from services.challenge_download import (
    challenge_download_filename,
    clean_text,
    clean_value,
    format_seconds,
    has_usable_video_url,
    prepare_challenge_zip,
)


def load_saved_recipients(
    supabase,
):
    try:
        response = (
            supabase
            .table("email_recipients")
            .select("*")
            .eq("active", True)
            .order("name")
            .execute()
        )

        return response.data or []

    except Exception:
        return []


def recipient_label(recipient):
    name = (
        clean_text(
            recipient.get("name")
        )
        or clean_text(
            recipient.get("email")
        )
        or "Recipient"
    )

    email = clean_text(
        recipient.get("email")
    )

    conference = clean_text(
        recipient.get("conference")
    )

    group_name = clean_text(
        recipient.get("group_name")
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
            + " • ".join(details)
        )

    return name


def default_recipient_ids(
    recipients,
    conference,
):
    conference_upper = (
        clean_text(conference)
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
                recipient.get("id")
            )

    return [
        item
        for item in defaults
        if item is not None
    ]


def split_manual_addresses(value):
    raw = clean_text(value)

    if not raw:
        return []

    normalized = (
        raw
        .replace(";", ",")
        .replace("\n", ",")
    )

    return [
        item.strip()
        for item in normalized.split(",")
        if item.strip()
    ]


def dedupe_addresses(values):
    result = []
    seen = set()

    for value in values:
        email = clean_text(value)

        if not email:
            continue

        key = email.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(email)

    return result


def default_subject(play):
    match_name = (
        clean_text(
            play.get("match_name")
        )
        or "Match"
    )

    set_number = clean_text(
        play.get("set_number")
    )

    score = clean_text(
        play.get("score")
    )

    ending = []

    if set_number:
        ending.append(
            f"Set {set_number}"
        )

    if score:
        ending.append(score)

    subject = (
        f"Challenge Review | "
        f"{match_name}"
    )

    if ending:
        subject += (
            " | "
            + ", ".join(ending)
        )

    return subject


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
    include_video_links,
    video_angles,
):
    lines = []

    if clean_text(custom_message):
        lines.extend(
            [
                clean_text(
                    custom_message
                ),
                "",
            ]
        )

    if include_basic:
        lines.extend(
            [
                "CHALLENGE INFORMATION",
                "---------------------",
                (
                    "Match: "
                    + clean_value(
                        play.get(
                            "match_name"
                        )
                    )
                ),
                (
                    "Date: "
                    + clean_value(
                        play.get(
                            "match_date"
                        )
                    )
                ),
                (
                    "Conference: "
                    + clean_value(
                        play.get(
                            "conference"
                        )
                    )
                ),
                (
                    "Set: "
                    + clean_value(
                        play.get(
                            "set_number"
                        )
                    )
                ),
                (
                    "Score: "
                    + clean_value(
                        play.get(
                            "score"
                        )
                    )
                ),
                (
                    "Challenging Team: "
                    + clean_value(
                        play.get(
                            "challenging_team"
                        )
                    )
                ),
                (
                    "DV Sport Challenge Type: "
                    + clean_value(
                        play.get(
                            "challenge_type"
                        )
                    )
                ),
                (
                    "Record Use: "
                    + (
                        "UNUSABLE — EXCLUDED FROM ANALYSIS / REPORTS"
                        if play.get(
                            "is_unusable"
                        ) is True
                        else "Usable"
                    )
                ),
                (
                    "Unusable Reason: "
                    + clean_value(
                        play.get(
                            "unusable_reason"
                        )
                    )
                    if play.get(
                        "is_unusable"
                    ) is True
                    else ""
                ),
                "",
            ]
        )

    if include_crs:
        lines.extend(
            [
                "CRS CLASSIFICATION",
                "------------------",
                (
                    "Category: "
                    + clean_value(
                        play.get(
                            "crs_category"
                        )
                    )
                ),
                (
                    "Touch Context: "
                    + clean_value(
                        play.get(
                            "crs_touch_context"
                        )
                    )
                ),
                (
                    "Original Decision: "
                    + clean_value(
                        play.get(
                            "crs_original_decision"
                        )
                    )
                ),
                "",
            ]
        )

    if include_result:
        changed_value = play.get(
            "crs_original_fault_changed"
        )

        changed_text = (
            "Yes"
            if changed_value is True
            else "No"
            if changed_value is False
            else "—"
        )

        lines.extend(
            [
                "CHALLENGE RESULT",
                "----------------",
                (
                    "Outcome: "
                    + clean_value(
                        play.get(
                            "crs_outcome"
                        )
                        or play.get(
                            "challenge_result"
                        )
                    )
                ),
                (
                    "Original Fault Decision Changed: "
                    + changed_text
                ),
                "",
            ]
        )

    if include_length:
        lines.extend(
            [
                (
                    "Challenge Length: "
                    + format_seconds(
                        play.get(
                            "challenge_length_seconds"
                        )
                    )
                ),
                "",
            ]
        )

    if include_review_tags:
        decision_value = play.get(
            "review_decision_correct"
        )

        decision_text = (
            "Correct"
            if decision_value is True
            else "Incorrect"
            if decision_value is False
            else "Not Tagged"
        )

        involved_roles = (
            play.get(
                "involved_roles"
            )
            or []
        )

        if not isinstance(
            involved_roles,
            list,
        ):
            involved_roles = [
                item.strip()
                for item in clean_text(
                    involved_roles
                ).split(",")
                if item.strip()
            ]

        lines.extend(
            [
                "REVIEW TAGS",
                "-----------",
                (
                    "Review Decision: "
                    + decision_text
                ),
                (
                    "Use for Training: "
                    + (
                        "Yes"
                        if play.get(
                            "use_for_training"
                        ) is True
                        else "No"
                    )
                ),
                (
                    "Who Was Involved: "
                    + (
                        ", ".join(
                            involved_roles
                        )
                        or "Not Tagged"
                    )
                ),
                (
                    "Names / Details: "
                    + clean_value(
                        play.get(
                            "involved_people"
                        )
                    )
                ),
                "",
            ]
        )

    if include_reviewer_notes:
        lines.extend(
            [
                "REVIEWER NOTES",
                "--------------",
                clean_value(
                    play.get(
                        "reviewer_notes"
                    )
                ),
                "",
            ]
        )

    if include_weekly_note:
        lines.extend(
            [
                "WEEKLY COORDINATOR NOTE",
                "-----------------------",
                clean_value(
                    play.get(
                        "weekly_summary_note"
                    )
                ),
                "",
            ]
        )

    if include_video_links:
        usable = [
            angle
            for angle in video_angles
            if has_usable_video_url(
                angle.get("video_url")
            )
        ]

        lines.extend(
            [
                "VIDEO ANGLES",
                "------------",
            ]
        )

        if usable:
            for angle in usable:
                lines.extend(
                    [
                        (
                            clean_value(
                                angle.get(
                                    "angle_name"
                                ),
                                "Video",
                            )
                        ),
                        clean_text(
                            angle.get(
                                "video_url"
                            )
                        ),
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    "No usable video URLs are available.",
                    "",
                ]
            )

    lines.extend(
        [
            "NCAA Women's Volleyball Review",
        ]
    )

    return "\n".join(lines)


def gmail_compose_url(
    to_addresses,
    cc_addresses,
    bcc_addresses,
    subject,
    body,
):
    params = {
        "view": "cm",
        "fs": "1",
        "to": ", ".join(
            to_addresses
        ),
        "cc": ", ".join(
            cc_addresses
        ),
        "bcc": ", ".join(
            bcc_addresses
        ),
        "su": subject,
        "body": body,
    }

    return (
        "https://mail.google.com/mail/?"
        + urlencode(params)
    )


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
            f"### "
            f"{clean_value(play.get('match_name'), 'Challenge')}"
        )
    )

    summary_parts = [
        clean_text(
            play.get("conference")
        ),
        (
            f"Set "
            f"{clean_text(play.get('set_number'))}"
            if clean_text(
                play.get("set_number")
            )
            else ""
        ),
        clean_text(
            play.get("score")
        ),
    ]

    st.caption(
        " • ".join(
            item
            for item in summary_parts
            if item
        )
    )

    recipients = load_saved_recipients(
        supabase
    )

    recipient_map = {
        recipient.get("id"):
            recipient
        for recipient in recipients
        if recipient.get("id")
        is not None
    }

    default_ids = default_recipient_ids(
        recipients,
        play.get("conference"),
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
                for item in default_ids
                if item
                in recipient_map
            ],
            format_func=lambda item:
                recipient_label(
                    recipient_map[item]
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
                "You can still enter addresses manually. "
                "Run the included Supabase SQL once to enable "
                "saved recipient defaults."
            )
        )

    r1, r2, r3 = st.columns(3)

    with r1:
        manual_to = st.text_area(
            "Additional To",
            height=92,
            placeholder=(
                "name@example.com, "
                "other@example.com"
            ),
            key=(
                f"{key_prefix}_to_"
                f"{play['id']}"
            ),
        )

    with r2:
        manual_cc = st.text_area(
            "CC",
            height=92,
            placeholder=(
                "Optional"
            ),
            key=(
                f"{key_prefix}_cc_"
                f"{play['id']}"
            ),
        )

    with r3:
        manual_bcc = st.text_area(
            "BCC",
            height=92,
            placeholder=(
                "Optional"
            ),
            key=(
                f"{key_prefix}_bcc_"
                f"{play['id']}"
            ),
        )

    saved_to = [
        clean_text(
            recipient_map[item]
            .get("email")
        )
        for item in selected_ids
        if item in recipient_map
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
            "Optional message to place above the "
            "challenge information."
        ),
        height=110,
        key=(
            f"{key_prefix}_message_"
            f"{play['id']}"
        ),
    )

    st.markdown(
        "#### Include in Email"
    )

    i1, i2 = st.columns(2)

    with i1:
        include_basic = st.checkbox(
            "Basic challenge information",
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

        include_reviewer_notes = (
            st.checkbox(
                "Reviewer notes",
                value=False,
                key=(
                    f"{key_prefix}_notes_"
                    f"{play['id']}"
                ),
            )
        )

        include_weekly_note = (
            st.checkbox(
                "Weekly coordinator note",
                value=False,
                key=(
                    f"{key_prefix}_weekly_"
                    f"{play['id']}"
                ),
            )
        )

        include_video_links = (
            st.checkbox(
                "Video angle links",
                value=False,
                key=(
                    f"{key_prefix}_links_"
                    f"{play['id']}"
                ),
                help=(
                    "These are DV Sport media URLs and may "
                    "expire. For permanent sharing, attach "
                    "the Challenge ZIP instead."
                ),
            )
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
        include_video_links=(
            include_video_links
        ),
        video_angles=video_angles,
    )

    with st.expander(
        "Preview Email Body"
    ):
        st.code(
            body,
            language=None,
            wrap_lines=True,
        )

    st.markdown(
        "#### Challenge Files"
    )

    usable_angles = [
        angle
        for angle in video_angles
        if has_usable_video_url(
            angle.get("video_url")
        )
    ]

    zip_state_key = (
        f"{key_prefix}_email_zip_"
        f"{play['id']}"
    )

    z1, z2 = st.columns(
        [
            1.0,
            1.0,
        ]
    )

    with z1:
        if st.button(
            "Prepare Challenge ZIP",
            use_container_width=True,
            key=(
                f"{key_prefix}_email_prepare_"
                f"{play['id']}"
            ),
        ):
            with st.spinner(
                (
                    f"Preparing ZIP with "
                    f"{len(usable_angles):,} video angle"
                    f"{'' if len(usable_angles) == 1 else 's'}..."
                )
            ):
                try:
                    st.session_state[
                        zip_state_key
                    ] = prepare_challenge_zip(
                        play,
                        usable_angles,
                    )

                except Exception as exc:
                    st.session_state.pop(
                        zip_state_key,
                        None,
                    )
                    st.error(
                        "The Challenge ZIP could not be prepared."
                    )
                    st.exception(exc)

    with z2:
        zip_data = (
            st.session_state.get(
                zip_state_key
            )
        )

        if zip_data:
            st.download_button(
                "Download Challenge ZIP",
                data=zip_data,
                file_name=challenge_download_filename(
                    play
                ),
                mime="application/zip",
                use_container_width=True,
                type="primary",
                key=(
                    f"{key_prefix}_email_download_"
                    f"{play['id']}"
                ),
            )
        else:
            st.button(
                "Download Challenge ZIP",
                disabled=True,
                use_container_width=True,
                key=(
                    f"{key_prefix}_email_download_disabled_"
                    f"{play['id']}"
                ),
            )

    st.caption(
        (
            "Gmail cannot receive a local attachment through a "
            "compose link. Download the ZIP here, open Gmail, "
            "then attach the ZIP in Gmail before sending."
        )
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
            2.0,
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
                "Opens Gmail compose with recipients, "
                "subject, and body prefilled."
            ),
        )

    if not to_addresses:
        st.caption(
            (
                "No To recipient is selected yet. Gmail will "
                "still open, and you can add one there."
            )
        )


def render_email_challenge_button(
    play,
    video_angles,
    supabase,
    key_prefix,
):
    if (
        clean_text(
            play.get("play_type")
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
