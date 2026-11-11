"""Pure VolleyReview sheet/export helpers. No credentials or network operations."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

CATEGORIES = ("Touch", "In/Out", "Net", "Attack Line", "Service Line / CenterLine")


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "null", "none", "<na>"} else text


def play_kind(value: Any) -> str:
    val = clean(value).upper()
    if val in ("CHALLENGE", "CHALLENGES"):
        return "Challenge"
    if val in ("FAULT", "FAULTS"):
        return "Fault"
    if val in ("POI", "POIS", "PLAY OF INTEREST", "PLAYS OF INTEREST"):
        return "POI"
    return clean(value) or "Unknown"


def category(value: Any) -> str:
    val = clean(value)
    s = val.upper()
    if val in CATEGORIES:
        return val
    if "TOUCH" in s or "CONTACT" in s:
        return "Touch"
    if any(x in s for x in ("IN/OUT", "IN / OUT", "BALL IN", "BALL OUT", "PANCAKE")):
        return "In/Out"
    if "NET" in s or "ANTENNA" in s:
        return "Net"
    if any(x in s for x in ("ATTACK LINE", "BACK-ROW", "BACK ROW", "LIBERO FRONT")):
        return "Attack Line"
    if any(x in s for x in ("SERVICE", "FOOT FAULT", "CENTER", "CENTRE", "CL FAULT")):
        return "Service Line / CenterLine"
    return val or "Other / Uncategorized"


def choose_category(play: dict[str, Any]) -> str:
    # Preserve the human-review classification ahead of imported source labels.
    for field in ("ncaa_challenge_category", "crs_category", "fault_category", "dvsport_crs_category", "challenge_type"):
        val = clean(play.get(field))
        if val:
            return category(val)
    return "Other / Uncategorized"


def parse_angles(raw: Any) -> list[dict[str, str]]:
    """Tolerates JSONB list/string and older dict forms, unique by URL."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if isinstance(raw, dict):
        if "video_urls" in raw:
            raw = raw["video_urls"]
        elif "angles" in raw:
            raw = raw["angles"]
        else:
            raw = [{"angle_name": k, "video_url": v} for k, v in raw.items()]
    if not isinstance(raw, list):
        return []
    result = []
    seen = set()
    for index, item in enumerate(raw):
        if isinstance(item, str):
            item = {"angle_name": f"Angle {index + 1}", "video_url": item}
        if not isinstance(item, dict):
            continue
        url = clean(item.get("video_url") or item.get("url") or item.get("source_url"))
        if not url.lower().startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        result.append({"name": clean(item.get("angle_name") or item.get("name")) or f"Angle {index + 1}", "url": url})
        if len(result) >= 30:
            break
    def order(angle: dict[str, str]):
        nm = angle["name"].upper()
        return (0 if nm == "PGM" else 1 if nm in ("REPLAY OUTPUT", "RO", "REPLAY") else 2, nm)
    return sorted(result, key=order)


def compact_metadata(play: dict[str, Any], angles: list[dict[str, str]], base_url: str,
                     signing_secret: str, link_days: int, app_url_template: str = "") -> dict[str, Any]:
    play_id = clean(play.get("id"))
    expires = int(time.time()) + max(1, link_days) * 86400
    signature = sign_download(play_id, expires, signing_secret)
    base = base_url.rstrip("/")
    download_url = f"{base}/api/v1/plays/{quote(play_id, safe='')}/download?expires={expires}&sig={signature}"
    app_url = app_url_template.replace("{id}", quote(play_id, safe="")) if "{id}" in app_url_template else ""
    judgment = clean(play.get("referee_judgment"))
    if not judgment and play.get("review_decision_correct") is not None:
        judgment = "Correct" if play["review_decision_correct"] is True else "Incorrect"
    return {
        "id": play_id,
        "match_date": clean(play.get("match_date")),
        "conference": clean(play.get("conference")),
        "match_name": clean(play.get("match_name")),
        "play_type": play_kind(play.get("play_type")),
        "category": choose_category(play),
        "set_number": play.get("set_number"),
        "score": clean(play.get("score")),
        "challenging_team": clean(play.get("challenging_team")),
        "original_call": clean(play.get("crs_original_decision")),
        "outcome": clean(play.get("crs_outcome") or play.get("challenge_result")),
        "outcome_detail": clean(play.get("challenge_outcome_detail")),
        "referee_judgment": judgment,
        "review_status": clean(play.get("review_status")),
        "challenge_length_seconds": play.get("challenge_length_seconds") or play.get("dvsport_challenge_length_seconds"),
        "starred": bool(play.get("is_starred")),
        "dvsport_category": clean(play.get("dvsport_crs_category") or play.get("challenge_type")),
        "dvsport_result": clean(play.get("challenge_result")),
        "reviewer_notes": clean(play.get("reviewer_notes")),
        "weekly_summary_note": clean(play.get("weekly_summary_note")),
        "training": bool(play.get("use_for_training")),
        "dvsport_id": clean(play.get("dvsport_id")),
        "dvsport_play_number": play.get("dvsport_play_number"),
        "download_url": download_url,
        "play_url": app_url,
        "angles": angles,
    }


def sign_download(play_id: str, expires: int, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{play_id}:{expires}".encode("utf-8"), hashlib.sha256).hexdigest()


def valid_download_token(play_id: str, expires: int, signature: str, secret: str) -> bool:
    if int(time.time()) > expires or expires > int(time.time()) + 45 * 86400:
        return False
    return hmac.compare_digest(sign_download(play_id, expires, secret), signature)


def safe_filename(value: Any, max_length: int = 90) -> str:
    result = re.sub(r'[^A-Za-z0-9._ -]+', '_', clean(value)).strip(" ._")
    return (result[:max_length].strip(" ._")) or "Unknown"


def zip_name(play: dict[str, Any]) -> str:
    parts = [
        safe_filename(play.get("match_date") or "Undated", 12),
        safe_filename(play.get("match_name") or "Match", 64),
        f"Set{safe_filename(play.get('set_number') or 'NA', 6)}",
        safe_filename(choose_category(play), 35),
        safe_filename(play.get("id"), 40),
    ]
    return "_".join(parts) + ".zip"


def info_text(play: dict[str, Any], angles: list[dict[str, str]], comments: list[dict[str, Any]]) -> str:
    keys = [
        ("Play ID", "id"), ("Match Date", "match_date"), ("Conference", "conference"),
        ("Match", "match_name"), ("Play Type", "play_type"), ("Set", "set_number"),
        ("Score", "score"), ("Challenging Team", "challenging_team"),
        ("Original Call", "crs_original_decision"), ("Challenge Outcome", "crs_outcome"),
        ("Source Outcome", "challenge_result"), ("Outcome Detail", "challenge_outcome_detail"),
        ("Referee Judgment", "referee_judgment"), ("Review Status", "review_status"),
        ("Reviewer Notes", "reviewer_notes"), ("Weekly Summary Note", "weekly_summary_note"),
        ("DV Sport ID", "dvsport_id"), ("DV Sport Play Number", "dvsport_play_number"),
    ]
    lines = ["VOLLEYREVIEW PLAY INFORMATION", "=============================", ""]
    lines.extend(f"{label}: {clean(play.get(field)) or '—'}" for label, field in keys)
    lines += ["", "VIDEO ANGLES", "------------"]
    lines.extend(f"{i}. {a['name']}" for i, a in enumerate(angles, 1))
    lines += ["", "SAVED COMMENTS", "--------------"]
    if not comments:
        lines.append("No comments saved.")
    for c in comments:
        lines.append(f"{clean(c.get('created_at'))} | {clean(c.get('author'))}: {clean(c.get('comment_text'))}")
        if c.get("tags"):
            lines.append("  Tags: " + ", ".join(c["tags"]))
    return "\n".join(lines) + "\n"
