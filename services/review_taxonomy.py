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
    if "REVER" in upper:
        return "Reversed"
    if "CONFIRM" in upper:
        return "Confirmed"
    if "STAND" in upper or "INCONCLUSIVE" in upper:
        return "Stands"
    if "MECHANICAL" in upper or "VIDEO FAIL" in upper or "TECHNICAL" in upper:
        return "Mechanical Failure"
    return text


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
