import re
import unicodedata
from typing import Iterable

from thefuzz import process


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

    result = process.extractOne(normalize_text(query), [normalize_text(c) for c in choices], score_cutoff=cutoff)
    if not result:
        return None

    match_index = [normalize_text(c) for c in choices].index(result[0])
    return choices[match_index]


def best_match_by_key(query: str, choices: list[str], key_func=None, cutoff: int = 70) -> str | None:
    if not choices:
        return None

    if key_func is None:
        return best_match(query, choices, cutoff=cutoff)

    normalized_choices = [key_func(item) for item in choices]
    target = normalize_text(query)
    result = process.extractOne(target, [normalize_text(item) for item in normalized_choices], score_cutoff=cutoff)

    if not result:
        return None

    return choices[normalized_choices.index(result[0])]
