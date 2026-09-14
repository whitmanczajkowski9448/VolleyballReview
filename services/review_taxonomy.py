import json

CHALLENGE_CATEGORIES = [
    "",
    "Touch",
    "In/Out",
    "Net",
    "Attack Line",
    "Service Line / CenterLine",
]

CHALLENGE_CATEGORY_LABELS = {
    "": "— Select —",
    "Touch": "1 — Touch",
    "In/Out": "2 — In/Out",
    "Net": "3 — Net",
    "Attack Line": "4 — Attack Line",
    "Service Line / CenterLine": "5 — Service Line / CenterLine",
}

ORIGINAL_CALLS = {
    "Touch": [
        "Touch",
        "No Touch",
    ],
    "In/Out": [
        "Ball In",
        "Ball Out",
        "Successful Pancake",
        "Unsuccessful Pancake",
    ],
    "Net": [
        "Net Fault",
        "No Net Fault",
    ],
    "Attack Line": [
        "Back-Row Attack",
        "Not a Back-Row Attack",
        "Libero in the Front Zone",
        "Libero not in the Front Zone",
    ],
    "Service Line / CenterLine": [
        "Foot Fault",
        "No Foot Fault",
        "Center Line Fault",
        "No Center Line Fault",
    ],
    "": [],
}

CHALLENGE_OUTCOMES = [
    "",
    "Confirmed",
    "Reversed",
    "Stands",
    "Mechanical Failure",
]

REFEREE_JUDGMENTS = [
    "",
    "Correct",
    "Incorrect",
    "Unclear",
]

REVIEW_STATUS_CHOICES = [
    "",
    "Needs Additional Review",
    "Complete",
]

NEW_FAULT_OPTIONS = []
for _category in CHALLENGE_CATEGORIES:
    for _call in ORIGINAL_CALLS.get(_category, []):
        if _call not in NEW_FAULT_OPTIONS:
            NEW_FAULT_OPTIONS.append(_call)


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_challenge_category(value):
    text = clean_text(value)
    upper = text.upper()

    if not text:
        return ""
    if text in CHALLENGE_CATEGORIES:
        return text
    if "TOUCH" in upper or "CONTACT" in upper:
        return "Touch"
    if "IN / OUT" in upper or "IN/OUT" in upper or "BALL IN" in upper or "BALL OUT" in upper or "PANCAKE" in upper:
        return "In/Out"
    if "NET" in upper or "ANTENNA" in upper:
        return "Net"
    if "ATTACK LINE" in upper or "BACK-ROW" in upper or "BACK ROW" in upper or "LIBERO FRONT" in upper:
        return "Attack Line"
    if "SERVICE" in upper or "FOOT FAULT" in upper or "CENTER" in upper or "CENTRE" in upper or "CL FAULT" in upper:
        return "Service Line / CenterLine"
    return text


def normalize_original_call(value):
    text = clean_text(value)
    if not text:
        return ""

    mapping = {
        "touch": "Touch",
        "no touch": "No Touch",
        "ball in": "Ball In",
        "ball out": "Ball Out",
        "successful pancake": "Successful Pancake",
        "unsuccessful pancake": "Unsuccessful Pancake",
        "net fault": "Net Fault",
        "no net fault": "No Net Fault",
        "back-row attack": "Back-Row Attack",
        "back row attack": "Back-Row Attack",
        "not a back-row attack": "Not a Back-Row Attack",
        "not a back row attack": "Not a Back-Row Attack",
        "libero in the front zone": "Libero in the Front Zone",
        "libero not in the front zone": "Libero not in the Front Zone",
        "foot fault": "Foot Fault",
        "no foot fault": "No Foot Fault",
        "cl fault": "Center Line Fault",
        "center-line fault": "Center Line Fault",
        "center line fault": "Center Line Fault",
        "no cl fault": "No Center Line Fault",
        "no center-line fault": "No Center Line Fault",
        "no center line fault": "No Center Line Fault",
    }
    return mapping.get(text.lower(), text)


def normalize_outcome(value):
    text = clean_text(value)
    if not text:
        return ""

    upper = text.upper()

    if (
        "MECHANICAL" in upper
        or "VIDEO FAIL" in upper
        or "TECHNICAL" in upper
    ):
        return "Mechanical Failure"

    if (
        "UNSUCCESS" in upper
        or "DENIED" in upper
        or "UPHELD" in upper
        or "CHALLENGE LOST" in upper
    ):
        return "Confirmed"

    if (
        "REVER" in upper
        or "OVERTURN" in upper
        or "SUCCESS" in upper
        or "GRANTED" in upper
        or "CHALLENGE WON" in upper
    ):
        return "Reversed"

    if "CONFIRM" in upper:
        return "Confirmed"

    if "STAND" in upper or "INCONCLUSIVE" in upper:
        return "Stands"

    return text


def imported_fault_comment(play):
    """Return the DV Sport COMMENTS value stored with an imported Fault."""
    metadata = play.get("dvsport_metadata") if isinstance(play, dict) else None

    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}

    if not isinstance(metadata, dict):
        return ""

    specialized = metadata.get("specialized")
    if not isinstance(specialized, dict):
        return ""

    fields = specialized.get("fields")
    if not isinstance(fields, dict):
        return ""

    return clean_text(
        fields.get("COMMENTS")
        or fields.get("COMMENT")
        or fields.get("Comments")
        or fields.get("Comment")
    )


def imported_fault_category(play):
    """Return the imported DV Sport FAULT category."""
    return (
        clean_text(play.get("dvsport_play_category"))
        or clean_text(play.get("play_category"))
    )


def fault_option_choices(plays=None):
    """Static NCAA calls plus unique DV Sport Fault comments already imported."""
    options = list(NEW_FAULT_OPTIONS)
    seen = {clean_text(item).casefold() for item in options if clean_text(item)}

    for play in plays or []:
        play_type = clean_text(play.get("play_type")).upper()
        if play_type not in {"FAULT", "FAULTS"}:
            continue

        label = imported_fault_comment(play)
        key = label.casefold()
        if label and key not in seen:
            options.append(label)
            seen.add(key)

    return options


def normalize_referee_judgment(value, legacy_boolean=None):
    text = clean_text(value)
    if text:
        lower = text.lower()
        if lower == "correct":
            return "Correct"
        if lower == "incorrect":
            return "Incorrect"
        if lower in {"unclear", "inconclusive"}:
            return "Unclear"
        return text
    if legacy_boolean is True:
        return "Correct"
    if legacy_boolean is False:
        return "Incorrect"
    return ""


def normalize_review_status(value):
    text = clean_text(value)
    if not text:
        return "Not Viewed"
    lower = text.lower()
    if lower == "complete":
        return "Complete"
    if lower in {"needs review", "needs additional review"}:
        return "Needs Additional Review"
    if lower == "not viewed":
        return "Not Viewed"
    return text


# Backward-compatible aliases for older imports.
NCAA_CHALLENGE_CATEGORIES = CHALLENGE_CATEGORIES
ORIGINAL_DECISIONS = ORIGINAL_CALLS
CRS_OUTCOMES = CHALLENGE_OUTCOMES
PLAY_TYPES = ["Challenge", "POI", "Fault"]
TOUCH_CONTEXTS = [""]
PLAY_CATEGORIES = [""]
