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

    upper = text.upper().strip()

    if upper in {"R", "REV", "REVERSED", "OVERTURNED"}:
        return "Reversed"
    if upper in {"C", "CONF", "CONFIRMED", "UPHELD"}:
        return "Confirmed"
    if upper in {"S", "STANDS", "INCONCLUSIVE"}:
        return "Stands"
    if upper in {"MF", "MECHANICAL FAILURE"}:
        return "Mechanical Failure"

    if (
        "MECHANICAL" in upper
        or "VIDEO FAIL" in upper
        or "VIDEO FAILURE" in upper
        or "TECHNICAL FAILURE" in upper
        or "EQUIPMENT FAIL" in upper
        or "NO VIDEO" in upper
    ):
        return "Mechanical Failure"

    # Check negative phrases before positive ones. For example,
    # UNSUCCESSFUL contains SUCCESSFUL and NO CHANGE contains CHANGE.
    if (
        "UNSUCCESS" in upper
        or "DENIED" in upper
        or "UPHELD" in upper
        or "CHALLENGE LOST" in upper
        or "CALL CONFIRMED" in upper
        or "RULING CONFIRMED" in upper
        or "NO CHANGE" in upper
        or "CALL UPHELD" in upper
    ):
        return "Confirmed"

    if (
        "REVER" in upper
        or "OVERTURN" in upper
        or "SUCCESS" in upper
        or "GRANTED" in upper
        or "CHALLENGE WON" in upper
        or "CALL CHANGED" in upper
        or "RULING CHANGED" in upper
    ):
        return "Reversed"

    if "CONFIRM" in upper:
        return "Confirmed"

    if (
        "STAND" in upper
        or "INCONCLUSIVE" in upper
        or "INSUFFICIENT EVIDENCE" in upper
        or "NO CONCLUSIVE" in upper
        or "NO DECISION" in upper
        or "UNABLE TO DETERMINE" in upper
    ):
        return "Stands"

    return text


CANONICAL_OUTCOMES = {
    "Confirmed",
    "Reversed",
    "Stands",
    "Mechanical Failure",
}


def canonical_outcome(value):
    normalized = normalize_outcome(value)
    return normalized if normalized in CANONICAL_OUTCOMES else ""


def _metadata_object(play):
    if play is None or not hasattr(play, "get"):
        return {}

    metadata = play.get("dvsport_metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}

    return metadata if isinstance(metadata, dict) else {}


def _result_key(value):
    return "".join(ch for ch in clean_text(value).upper() if ch.isalnum())


def _is_result_heading(value):
    key = _result_key(value)
    if not key:
        return False

    exact = {
        "REVIEWRESULT",
        "CHALLENGERESULT",
        "REVIEWOUTCOME",
        "CHALLENGEOUTCOME",
        "CRSRESULT",
        "CRSOUTCOME",
        "RESULT",
        "OUTCOME",
        "REVIEWDECISION",
        "CHALLENGEDECISION",
        "CRSDECISION",
        "REVIEWSTATUS",
        "CHALLENGESTATUS",
        "CRSSTATUS",
        "REVIEWSUCCESS",
        "REVIEWSUCCESSFUL",
        "CHALLENGESUCCESS",
        "CHALLENGESUCCESSFUL",
        "REVIEWDISPOSITION",
        "CHALLENGEDISPOSITION",
        "REVIEWRULING",
        "CHALLENGERULING",
    }
    if key in exact:
        return True

    has_result_word = any(
        word in key
        for word in (
            "RESULT",
            "OUTCOME",
            "DECISION",
            "STATUS",
            "SUCCESS",
            "DISPOSITION",
            "RULING",
        )
    )
    has_source_word = any(word in key for word in ("REVIEW", "CHALLENGE", "CRS"))
    return has_result_word and has_source_word


def _display_values(value):
    """Yield human-readable scalar candidates from a DV Sport value object."""
    if value is None:
        return

    if isinstance(value, dict):
        preferred = (
            "displayValue", "DisplayValue", "displayText", "DisplayText",
            "formattedValue", "FormattedValue", "label", "Label",
            "text", "Text", "name", "Name", "title", "Title",
            "fieldData", "fielddata", "value", "Value",
        )
        seen_keys = set()
        for key in preferred:
            if key in value:
                seen_keys.add(key)
                yield from _display_values(value.get(key))
        for key, nested in value.items():
            if key not in seen_keys:
                yield from _display_values(nested)
        return

    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _display_values(item)
        return

    text = clean_text(value)
    if text:
        yield text


def _canonical_candidate(value):
    for candidate in _display_values(value):
        if canonical_outcome(candidate):
            return candidate
    return ""


def _heading_candidate(heading, value):
    """Resolve one DV Sport result field, including success booleans."""
    candidate = _canonical_candidate(value)
    if candidate:
        return candidate

    heading_key = _result_key(heading)
    if "SUCCESS" not in heading_key:
        return ""

    # Some playlist versions expose challenge success as a boolean instead of
    # a display string. A successful challenge changes the ruling (Reversed);
    # an unsuccessful challenge leaves the ruling in place (Confirmed).
    for raw in _display_values(value):
        token = clean_text(raw).strip().upper()
        if token in {"TRUE", "YES", "Y", "1"}:
            return "Reversed"
        if token in {"FALSE", "NO", "N", "0"}:
            return "Confirmed"

    if value is True:
        return "Reversed"
    if value is False:
        return "Confirmed"
    return ""


def imported_challenge_result(play):
    """Recover the DV Sport challenge result from stored source data.

    Existing databases may have blank challenge_result values even though the
    original DV Sport fields were retained inside dvsport_metadata. This helper
    reads both locations so old imports can be resolved without deleting data.
    """
    if play is None or not hasattr(play, "get"):
        return ""

    direct = clean_text(play.get("challenge_result"))
    if canonical_outcome(direct):
        return direct

    metadata = _metadata_object(play)
    specialized = metadata.get("specialized") if isinstance(metadata, dict) else None
    if not isinstance(specialized, dict):
        return direct

    fields = specialized.get("fields")
    if isinstance(fields, dict):
        # Prefer recognized result/outcome/decision headings only. This avoids
        # accidentally interpreting values such as "Successful Pancake" as a
        # challenge result.
        for key, value in fields.items():
            if not _is_result_heading(key):
                continue
            candidate = _heading_candidate(key, value)
            if candidate:
                return candidate

    verbose = specialized.get("data_verbose") or specialized.get("DataVerbose") or []
    if isinstance(verbose, list):
        for entry in verbose:
            if not isinstance(entry, dict):
                continue
            heading = (
                entry.get("internalName")
                or entry.get("internalname")
                or entry.get("displayName")
                or entry.get("DisplayName")
                or entry.get("fieldName")
                or entry.get("FieldName")
                or entry.get("name")
                or entry.get("Name")
                or entry.get("label")
                or entry.get("Label")
            )
            if not _is_result_heading(heading):
                continue

            candidate = _heading_candidate(heading, entry)
            if candidate:
                return candidate

    return direct


def resolve_challenge_outcome(play):
    """Return the effective challenge outcome used throughout VolleyReview.

    A coordinator-entered crs_outcome always wins. Otherwise use the DV Sport
    result, including the copy preserved in dvsport_metadata for older imports.
    """
    if play is None or not hasattr(play, "get"):
        return ""

    stored = canonical_outcome(play.get("crs_outcome"))
    if stored:
        return stored

    return canonical_outcome(imported_challenge_result(play))


def coerce_challenge_length_seconds(value):
    """Convert a stored/imported challenge length to whole seconds."""
    if value is None:
        return None

    text = clean_text(value)
    if not text:
        return None

    if ":" in text:
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            minutes = int(parts[0])
            seconds = int(parts[1])
        except (TypeError, ValueError):
            return None
        if minutes < 0 or seconds < 0 or seconds >= 60:
            return None
        return minutes * 60 + seconds

    try:
        seconds = int(float(text))
    except (TypeError, ValueError):
        return None

    return seconds if seconds >= 0 else None


def _is_length_heading(name):
    upper = clean_text(name).upper()
    if not upper:
        return False
    if upper in {
        "REVIEW TIME",
        "CHALLENGE TIME",
        "REVIEW LENGTH",
        "CHALLENGE LENGTH",
        "REVIEW DURATION",
        "CHALLENGE DURATION",
    }:
        return True
    return (
        any(token in upper for token in ("REVIEW", "CHALLENGE", "CRS"))
        and any(token in upper for token in ("TIME", "LENGTH", "DURATION"))
    )


def imported_challenge_length_seconds(play):
    """Return DV Sport's challenge length, including metadata fallback.

    Older rows may have a blank dvsport_challenge_length_seconds column even
    though REVIEW TIME was preserved in dvsport_metadata.specialized.fields.
    """
    if play is None or not hasattr(play, "get"):
        return None

    direct = coerce_challenge_length_seconds(
        play.get("dvsport_challenge_length_seconds")
    )
    if direct is not None:
        return direct

    metadata = _metadata_object(play)
    specialized = metadata.get("specialized") if isinstance(metadata, dict) else None
    if not isinstance(specialized, dict):
        return None

    fields = specialized.get("fields")
    if isinstance(fields, dict):
        preferred = [
            "REVIEW TIME",
            "CHALLENGE TIME",
            "REVIEW LENGTH",
            "CHALLENGE LENGTH",
            "REVIEW DURATION",
            "CHALLENGE DURATION",
        ]
        lookup = {clean_text(k).upper(): v for k, v in fields.items()}
        for name in preferred:
            parsed = coerce_challenge_length_seconds(lookup.get(name))
            if parsed is not None:
                return parsed

        for key, value in fields.items():
            if not _is_length_heading(key):
                continue
            parsed = coerce_challenge_length_seconds(value)
            if parsed is not None:
                return parsed

    verbose = specialized.get("data_verbose") or specialized.get("DataVerbose") or []
    if isinstance(verbose, list):
        for entry in verbose:
            if not isinstance(entry, dict):
                continue
            heading = (
                entry.get("internalName")
                or entry.get("internalname")
                or entry.get("displayName")
                or entry.get("DisplayName")
                or entry.get("fieldName")
                or entry.get("FieldName")
                or entry.get("name")
                or entry.get("Name")
                or entry.get("label")
                or entry.get("Label")
            )
            if not _is_length_heading(heading):
                continue
            for value_key in ("value", "Value", "displayValue", "DisplayValue", "text", "Text"):
                parsed = coerce_challenge_length_seconds(entry.get(value_key))
                if parsed is not None:
                    return parsed

    return None


def resolve_challenge_length_seconds(play):
    """Return the effective length used by Tag/Edit, Dashboard, and reports.

    A coordinator-entered challenge_length_seconds value wins. Otherwise use
    the DV Sport source value, including metadata fallback for older imports.
    """
    if play is None or not hasattr(play, "get"):
        return None

    stored = coerce_challenge_length_seconds(play.get("challenge_length_seconds"))
    if stored is not None:
        return stored

    return imported_challenge_length_seconds(play)


def challenge_length_override_state(play):
    """Return True/False for an explicit length override, or None if unknown."""
    metadata = _metadata_object(play)
    if not isinstance(metadata, dict):
        return None

    overrides = metadata.get("volleyreview_overrides")
    if not isinstance(overrides, dict) or "challenge_length" not in overrides:
        return None

    return bool(overrides.get("challenge_length"))

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
