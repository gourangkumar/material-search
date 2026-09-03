
from __future__ import annotations

import re
from typing import Any


STOP_WORDS = {
    "generic", "make", "brand", "item", "code", "product", "products",
    "material", "materials", "with", "compatible", "for", "using",
    "of", "the", "and", "or", "type", "size", "colour", "color", "new",
    "invoice", "po", "pono", "purchase", "serial", "serialno", "imei",
    "quality", "no", "number", "model", "modelno",
}

_UNIT_PREFIXES = (
    r"(?:MM|CM|KG|ML|KW|HP|RPM|AWG|SWG|PSI|NB|ID|OD|IN|M|V|A|W|L|G)"
)

_MEASUREMENT_UNITS = (
    r"(?:mm2|sqmm|sqcm|mm|cm|km|kg|gms?|gsm|mg|ml|ltr|litre|litres|"
    r"kw|hp|rpm|psi|bar|kv|v|w|amps?|a|awg|swg|inch|in|ft|nb|id|od|"
    r"pin|phase|cores?|c|m|l|g)"
)

_MEASUREMENT_TOKEN_RE = re.compile(
    rf"^\d+(?:\.\d+)?{_MEASUREMENT_UNITS}$",
    re.IGNORECASE,
)

# Thread/dimension forms such as M8, M8X20, ID08 and OD2.
_PREFIXED_MEASUREMENT_RE = re.compile(
    r"^(?:m|id|od|nb|awg|swg)\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?$",
    re.IGNORECASE,
)

_MODEL_LABEL_RE = re.compile(
    r"\b(?:model|part|item)\s*(?:no\.?|number|code)?\s*[:#-]?\s*"
    r"([a-z0-9][a-z0-9./-]*)",
    re.IGNORECASE,
)

_COMPOUND_CODE_RE = re.compile(
    r"\b[A-Z0-9]+(?:[-/][A-Z0-9]+)+\b",
    re.IGNORECASE,
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN/NaT without requiring pandas.
    except Exception:
        return False


def _insert_unit_prefix_boundary(text: str) -> str:
    """Turn SCREWM8 into SCREW M8 without breaking genuine model codes."""
    return re.sub(rf"(?<=[A-Z])(?={_UNIT_PREFIXES}\d)", " ", text)


def _is_measurement_token(token: str) -> bool:
    value = token.strip("-/").lower()
    return bool(
        _MEASUREMENT_TOKEN_RE.fullmatch(value)
        or _PREFIXED_MEASUREMENT_RE.fullmatch(value)
        or re.fullmatch(r"x\d+(?:\.\d+)?", value)
    )


def extract_model_numbers(text: Any) -> str:
    """Extract genuine model/part codes while excluding measurements.

    Examples retained: A9F74106, WDS500-G2B0A, 4H-210-08, 6205-2RS.
    Examples excluded: 4C, 16SQMM, 20MM, 230V, 10AMP, M8, M8X20.
    A purely numeric or measurement-like value is retained only when explicitly
    introduced by a model/part/item label.
    """
    if _is_missing(text):
        return ""

    source = str(text).upper()
    codes: list[str] = []

    # Explicit labels are authoritative, including numeric-only part numbers.
    for match in _MODEL_LABEL_RE.finditer(source):
        code = match.group(1).strip("-/")
        if code:
            codes.append(code)

    # Preserve compound identifiers, but do not promote plain dimension chains.
    for match in _COMPOUND_CODE_RE.finditer(source):
        code = match.group().strip("-/")
        if any(ch.isalpha() for ch in code) and any(ch.isdigit() for ch in code):
            if not _is_measurement_token(code):
                codes.append(code)

    remainder = _COMPOUND_CODE_RE.sub(" ", source)
    remainder = _MODEL_LABEL_RE.sub(" ", remainder)
    remainder = _insert_unit_prefix_boundary(remainder)
    remainder = re.sub(r"[^A-Z0-9/\-\s]", " ", remainder)

    for token in remainder.split():
        token = token.strip("-/")
        if len(token) < 2 or _is_measurement_token(token):
            continue
        if any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token):
            codes.append(token)

    seen: set[str] = set()
    output: list[str] = []
    for code in codes:
        normalized = code.lower()
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return " ".join(output)


def _split_alnum_boundaries(text: str) -> str:
    """Separate a fused word from an engineering unit prefix.

    This intentionally does not split every letter-number boundary, because
    doing so would damage identifiers such as A9F74106 and 6205ZZ.
    """
    return _insert_unit_prefix_boundary(text.upper()).lower()


def clean_general_text(text: Any, split_alnum: bool = True) -> str:
    """Clean ERP text consistently while retaining useful engineering terms."""
    if _is_missing(text):
        return ""

    value = str(text).lower()
    value = re.sub(r"_x000d_", " ", value, flags=re.IGNORECASE)

    # Canonical unit spellings.
    value = re.sub(r"\b(\d+(?:\.\d+)?)\s*mm2\b", r"\1sqmm", value)
    value = re.sub(r"\bsq\.?\s*mm\b", "sqmm", value)
    value = re.sub(r"\bsq\.?\s*cm\b", "sqcm", value)

    # Remove ERP labels and reference values that should not drive relevance.
    value = re.sub(r"item\s*code\s*[:-]?", " ", value)
    value = re.sub(r"product\s*code\s*[:-]?", " ", value)
    value = re.sub(r"po\s*no\.?\s*[:-]?\s*\S+", " ", value)
    value = re.sub(r"invoice\s*no\.?\s*[:-]?\s*\S+", " ", value)
    value = re.sub(r"imei\s*no\.?\s*[:-]?\s*\S+", " ", value)
    value = re.sub(r"serial\s*no\.?\s*[:-]?\s*\S+", " ", value)

    value = re.sub(r"[^a-z0-9./x+\- ]+", " ", value)
    if split_alnum:
        value = _split_alnum_boundaries(value)
    value = re.sub(r"\s+", " ", value).strip()

    tokens = [
        token
        for token in value.split()
        if token not in STOP_WORDS
        and not re.fullmatch(r"[.\-/x+]+", token)
    ]

    seen: set[str] = set()
    output: list[str] = []
    for token in tokens:
        if token not in seen:
            output.append(token)
            seen.add(token)
    return " ".join(output)


def dehyphenate_model_numbers(model_numbers: str) -> str:
    """Return additional code forms with internal dashes/slashes removed."""
    if not model_numbers:
        return ""

    seen: set[str] = set()
    output: list[str] = []
    for token in str(model_numbers).split():
        stripped = token.replace("-", "").replace("/", "")
        if stripped and stripped not in seen:
            output.append(stripped)
            seen.add(stripped)
    return " ".join(output)


def clean_and_extract(raw_text: Any) -> dict[str, str]:
    """Return the two canonical fields used by indexing and searching."""
    return {
        "general_text": clean_general_text(raw_text, split_alnum=True),
        "model_numbers": extract_model_numbers(raw_text),
    }
