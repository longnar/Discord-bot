import difflib
import re
import unicodedata
from typing import Iterable

try:
    from thefuzz import process
    HAS_THEFUZZ = True
except ImportError:
    HAS_THEFUZZ = False


def normalize_text(value: str) -> str:
    if value is None:
        return ""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def best_match(query: str, choices: Iterable[str], cutoff: int = 70) -> str | None:
    choices = list(choices)
    if not choices:
        return None

    normalized_query = normalize_text(query)
    normalized_choices = [normalize_text(c) for c in choices]

    if HAS_THEFUZZ:
        result = process.extractOne(normalized_query, normalized_choices, score_cutoff=cutoff)
        if not result:
            return None
        match_index = normalized_choices.index(result[0])
        return choices[match_index]
    else:
        # Fallback to difflib
        cutoff_ratio = cutoff / 100.0
        matches = difflib.get_close_matches(normalized_query, normalized_choices, n=1, cutoff=cutoff_ratio)
        if not matches:
            return None
        match_index = normalized_choices.index(matches[0])
        return choices[match_index]


def best_match_by_key(query: str, choices: list, key_func=None, cutoff: int = 70) -> str | None:
    if not choices:
        return None

    if key_func is None:
        return best_match(query, choices, cutoff=cutoff)

    normalized_choices = [key_func(item) for item in choices]
    target = normalize_text(query)

    if HAS_THEFUZZ:
        result = process.extractOne(target, [normalize_text(item) for item in normalized_choices], score_cutoff=cutoff)
        if not result:
            return None
        return choices[normalized_choices.index(result[0])]
    else:
        cutoff_ratio = cutoff / 100.0
        norm_targets = [normalize_text(item) for item in normalized_choices]
        matches = difflib.get_close_matches(target, norm_targets, n=1, cutoff=cutoff_ratio)
        if not matches:
            return None
        return choices[norm_targets.index(matches[0])]
