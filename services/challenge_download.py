import io
import re
import zipfile

import requests
import streamlit as st


def clean_text(value):
    if value is None:
        return ""

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


def clean_value(value, fallback="—"):
    text = clean_text(value)
    return text if text else fallback


def has_usable_video_url(value):
    url = clean_text(value)

    if not url:
        return False

    lowered = url.lower()

    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
    )


def safe_filename(value, fallback="File"):
    text = clean_text(value) or fallback

    text = re.sub(
        r'[<>:"/\\|?*]+',
        "_",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text[:120] or fallback


def media_extension(url, content_type=""):
    path = (
        clean_text(url)
        .split("?")[0]
        .lower()
    )

    for extension in (
        ".mp4",
        ".m4v",
        ".mov",
        ".webm",
        ".m3u8",
    ):
        if path.endswith(extension):
            return extension

    content_type = (
        clean_text(content_type)
        .lower()
    )

    if "mp4" in content_type:
        return ".mp4"

    if "quicktime" in content_type:
        return ".mov"

    if "webm" in content_type:
        return ".webm"

    if "mpegurl" in content_type:
        return ".m3u8"

    return ".mp4"


def format_seconds(value):
    if value is None:
        return "—"

    try:
        total = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return "—"

    return (
        f"{total // 60}:"
        f"{total % 60:02d}"
    )


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


def challenge_info_text(
    play,
    video_angles,
):
    judgment = clean_text(play.get("referee_judgment"))
    if not judgment:
        legacy = play.get("review_decision_correct")
        judgment = "Correct" if legacy is True else "Incorrect" if legacy is False else "—"

    length_value = play.get("challenge_length_seconds")
    if length_value is None:
        length_value = play.get("dvsport_challenge_length_seconds")

    lines = [
        "NCAA WOMEN'S VOLLEYBALL CHALLENGE REVIEW",
        "=" * 46,
        "",
        f"Conference: {clean_value(play.get('conference'))}",
        f"Match Date: {clean_value(play.get('match_date'))}",
        f"Match: {clean_value(play.get('match_name'))}",
        f"Set: {clean_value(play.get('set_number'))}",
        f"Score: {clean_value(play.get('score'))}",
        f"Challenging Team: {clean_value(play.get('challenging_team'))}",
        f"DV Sport Category: {clean_value(play.get('dvsport_crs_category') or play.get('challenge_type'))}",
        f"DV Sport Result: {clean_value(play.get('challenge_result'))}",
        "",
        "VOLLEYREVIEW CLASSIFICATION",
        "-" * 28,
        f"Challenge Category: {clean_value(play.get('ncaa_challenge_category') or play.get('crs_category'))}",
        f"Original Call: {clean_value(play.get('crs_original_decision'))}",
        f"Challenge Outcome: {clean_value(play.get('crs_outcome') or play.get('challenge_result'))}",
        f"Fault Changed / New Fault: {clean_value(play.get('challenge_outcome_detail'))}",
        f"Referee Judgment: {judgment}",
        f"Challenge Length: {format_seconds(length_value)}",
        f"Review Status: {clean_value(play.get('review_status'), 'Not Viewed')}",
        f"Starred: {'Yes' if play.get('is_starred') is True else 'No'}",
        "",
        "WEEKLY COORDINATOR NOTE",
        "-" * 23,
        clean_value(play.get("weekly_summary_note")),
        "",
        "VIDEO ANGLES INCLUDED",
        "-" * 21,
    ]

    usable_angles = [
        angle
        for angle in video_angles
        if has_usable_video_url(angle.get("video_url"))
    ]

    if usable_angles:
        for index, angle in enumerate(usable_angles, start=1):
            lines.append(
                f"{index}. {clean_value(angle.get('angle_name'), 'Video')}"
            )
    else:
        lines.append("None")

    lines.extend([
        "",
        f"DV Sport ID: {clean_value(play.get('dvsport_id'))}",
        f"Database Play ID: {clean_value(play.get('id'))}",
    ])

    return "\n".join(lines)


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def build_challenge_zip(
    play_signature,
    angle_signature,
):
    play_data = dict(
        play_signature
    )

    angle_rows = [
        dict(row)
        for row in angle_signature
    ]

    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:

        archive.writestr(
            "Challenge_Info.txt",
            challenge_info_text(
                play_data,
                angle_rows,
            ),
        )

        used_names = set()

        for index, angle in enumerate(
            angle_rows,
            start=1,
        ):
            url = clean_text(
                angle.get("video_url")
            )

            if not has_usable_video_url(
                url
            ):
                continue

            try:
                response = requests.get(
                    url,
                    stream=True,
                    timeout=90,
                    allow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 "
                            "(Windows NT 10.0; Win64; x64)"
                        )
                    },
                )

                try:
                    if response.status_code not in {
                        200,
                        206,
                    }:
                        continue

                    content_type = (
                        response.headers
                        .get(
                            "Content-Type",
                            "",
                        )
                    )

                    lowered_type = (
                        content_type.lower()
                    )

                    if (
                        lowered_type.startswith(
                            "text/"
                        )
                        or "html"
                        in lowered_type
                        or "json"
                        in lowered_type
                    ):
                        continue

                    angle_name = safe_filename(
                        angle.get(
                            "angle_name"
                        ),
                        f"Angle_{index:02d}",
                    )

                    extension = media_extension(
                        url,
                        content_type,
                    )

                    filename = (
                        f"{index:02d}_"
                        f"{angle_name}"
                        f"{extension}"
                    )

                    duplicate_number = 2

                    while (
                        filename.lower()
                        in used_names
                    ):
                        filename = (
                            f"{index:02d}_"
                            f"{angle_name}_"
                            f"{duplicate_number}"
                            f"{extension}"
                        )
                        duplicate_number += 1

                    used_names.add(
                        filename.lower()
                    )

                    with archive.open(
                        filename,
                        mode="w",
                    ) as destination:
                        for chunk in (
                            response.iter_content(
                                chunk_size=(
                                    1024
                                    * 1024
                                ),
                            )
                        ):
                            if chunk:
                                destination.write(
                                    chunk
                                )

                finally:
                    response.close()

            except requests.RequestException:
                continue

    buffer.seek(0)
    return buffer.getvalue()


def build_play_signature(play):
    fields = {
        key: play.get(key)
        for key in [
            "id",
            "dvsport_id",
            "conference",
            "match_date",
            "match_name",
            "play_type",
            "set_number",
            "score",
            "challenging_team",
            "challenge_type",
            "dvsport_crs_category",
            "challenge_result",
            "review_status",
            "weekly_summary_note",
            "ncaa_challenge_category",
            "crs_category",
            "crs_original_decision",
            "crs_outcome",
            "challenge_outcome_detail",
            "challenge_length_seconds",
            "dvsport_challenge_length_seconds",
            "referee_judgment",
            "review_decision_correct",
            "is_starred",
        ]
    }

    return tuple(sorted(fields.items()))


def build_angle_signature(video_angles):
    usable_angles = [
        angle
        for angle in video_angles
        if has_usable_video_url(
            angle.get("video_url")
        )
    ]

    return tuple(
        tuple(
            sorted(
                {
                    "angle_name":
                        angle.get(
                            "angle_name"
                        ),
                    "video_url":
                        angle.get(
                            "video_url"
                        ),
                }.items()
            )
        )
        for angle in usable_angles
    )


def challenge_download_filename(play):
    match_name = safe_filename(
        play.get("match_name"),
        "Challenge",
    )

    match_date = (
        clean_text(
            play.get("match_date")
        )
        .replace("-", "")
    )

    set_number = (
        clean_text(
            play.get("set_number")
        )
        or "NA"
    )

    score = safe_filename(
        play.get("score"),
        "Score",
    )

    parts = [
        part
        for part in [
            match_date,
            match_name,
            f"Set{set_number}",
            score,
            "Challenge",
        ]
        if part
    ]

    return (
        "_".join(parts)
        + ".zip"
    )


def prepare_challenge_zip(
    play,
    video_angles,
):
    return build_challenge_zip(
        build_play_signature(
            play
        ),
        build_angle_signature(
            video_angles
        ),
    )


def render_challenge_download(
    play,
    video_angles,
    key_prefix,
):
    if normalized_play_type(
        play.get("play_type")
    ) != "Challenge":
        return

    usable_angles = [
        angle
        for angle in video_angles
        if has_usable_video_url(
            angle.get("video_url")
        )
    ]

    state_key = (
        f"{key_prefix}_challenge_zip_"
        f"{play['id']}"
    )

    if st.button(
        "⬇ Download Challenge",
        use_container_width=True,
        key=(
            f"{key_prefix}_prepare_zip_"
            f"{play['id']}"
        ),
        help=(
            "Prepare a ZIP containing every available "
            "video angle plus Challenge_Info.txt."
        ),
    ):
        with st.spinner(
            (
                f"Preparing challenge ZIP with "
                f"{len(usable_angles):,} video angle"
                f"{'' if len(usable_angles) == 1 else 's'}..."
            )
        ):
            try:
                st.session_state[
                    state_key
                ] = prepare_challenge_zip(
                    play,
                    usable_angles,
                )

            except Exception as exc:
                st.session_state.pop(
                    state_key,
                    None,
                )
                st.error(
                    "The challenge ZIP could not be prepared."
                )
                st.exception(exc)

    zip_data = st.session_state.get(
        state_key
    )

    if zip_data:
        st.download_button(
            "Download Prepared ZIP",
            data=zip_data,
            file_name=challenge_download_filename(
                play
            ),
            mime="application/zip",
            use_container_width=True,
            type="primary",
            key=(
                f"{key_prefix}_download_zip_"
                f"{play['id']}"
            ),
        )

        st.caption(
            (
                f"{len(usable_angles):,} usable video angle"
                f"{'' if len(usable_angles) == 1 else 's'} "
                "+ Challenge_Info.txt"
            )
        )
