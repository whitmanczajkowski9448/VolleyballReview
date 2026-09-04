import json

from services.dvsport_media import fresh_video_url


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalized_angle_name(value):
    return clean_text(value).upper()


def is_program(angle):
    return normalized_angle_name(angle.get("angle_name")) in {
        "PGM",
        "PROGRAM",
        "PROGRAM FEED",
        "PROGRAM OUTPUT",
    }


def is_replay(angle):
    return normalized_angle_name(angle.get("angle_name")) in {
        "REPLAY OUTPUT",
        "RO",
        "REPLAY",
        "REPLAY OUT",
    }


def video_sort_key(angle):
    if is_program(angle):
        return (0, "")
    if is_replay(angle):
        return (1, "")
    return (2, normalized_angle_name(angle.get("angle_name")))


def has_usable_video_url(value):
    text = clean_text(value)
    return bool(text and text.lower() not in {"none", "null", "nan", "<na>"})


def video_angles_from_play(play, limit=30):
    raw = play.get("video_urls") or []

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = []

    if isinstance(raw, dict):
        raw = [
            {"angle_name": name, "video_url": url}
            for name, url in raw.items()
        ]

    if not isinstance(raw, list):
        raw = []

    result = []

    for index, item in enumerate(raw[:limit], start=1):
        if not isinstance(item, dict):
            continue

        source_url = clean_text(
            item.get("video_url")
            or item.get("url")
            or item.get("source_url")
        )
        if not has_usable_video_url(source_url):
            continue

        angle_name = clean_text(
            item.get("angle_name")
            or item.get("name")
        ) or f"Video {index}"

        sas_error = ""
        try:
            playable_url = fresh_video_url(source_url) or source_url
        except Exception as exc:
            playable_url = source_url
            sas_error = str(exc)

        result.append(
            {
                "id": clean_text(item.get("id")) or f"angle-{index}",
                "angle_name": angle_name,
                "video_url": playable_url,
                "source_url": source_url,
                "media_name": clean_text(item.get("media_name") or item.get("filename")),
                "sas_error": sas_error,
            }
        )

    result.sort(key=video_sort_key)
    return result
