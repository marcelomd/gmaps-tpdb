import re
from difflib import SequenceMatcher

# Treatments are separated by ";" or by a comma followed by a space ("a, b").
# A bare comma is left alone because chemical names use it ("1,2-dichloroethane").
TREATMENT_SEPARATORS = re.compile(r";|,\s")

SIMILARITY_CUTOFF = 0.85


def clean(value):
    """Trim and collapse whitespace (including non-breaking spaces); case is kept"""
    return " ".join(str(value).split())


def norm_key(value):
    """Identity of a name: two spellings with the same key are the same entry"""
    return clean(value).casefold()


def split_treatments(text):
    """Split a cell into distinct treatment names, dropping blanks and case duplicates"""
    names = {}
    for part in TREATMENT_SEPARATORS.split(text):
        name = clean(part)
        if name:
            names.setdefault(norm_key(name), name)
    return list(names.values())


def similar_keys(key, existing_keys):
    """Existing keys close enough to `key` to be a typo or variant of it, best match first"""
    scored = []
    for other in existing_keys:
        if other == key:
            continue
        ratio = SequenceMatcher(None, key, other).ratio()
        if ratio >= SIMILARITY_CUTOFF:
            scored.append((ratio, other))
    return [other for _, other in sorted(scored, reverse=True)]
