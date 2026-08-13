"""
Shared text-cleaning / model-number-extraction logic.

CRITICAL: this module must be imported by BOTH preprocess.py (index side)
and evaluate_search.py (query side). Using two different cleaning
pipelines for the same match is the #1 cause of query/document mismatch.
"""
import re
import pandas as pd

# -------------------------------------------------------
# Stop words
# -------------------------------------------------------
# "generic" is deliberately included: it is both an ERP placeholder brand
# label (used even when the real item is branded) AND a genuinely common
# brandName in the catalog for unbranded items. Either way it carries no
# discriminating signal and, left in, drowns out real signal via TF weighting.
STOP_WORDS = {
    "generic", "make", "brand", "item", "code", "product", "products",
    "material", "materials", "with", "compatible", "for", "using",
    "of", "the", "and", "or", "type", "size", "colour", "color", "new",
    "invoice", "po", "pono", "purchase", "serial", "serialno", "imei",
    "quality", "no", "number", "model", "modelno",
}

# Unit / dimension prefixes commonly fused directly onto a number in MRO
# descriptions (e.g. "M8", "ID08", "OD2"). Used to force a split so
# "screwm8" -> "screw m8" instead of staying fused.
_UNIT_PREFIXES = r"(?:MM|CM|KG|ML|KW|HP|RPM|AWG|SWG|PSI|NB|ID|OD|IN|M|V|A|W|L|G)"


def _insert_unit_prefix_boundary(text: str) -> str:
    """Insert a space before a unit-prefix+digit run that's fused onto a
    preceding word, e.g. 'SCREWM8' -> 'SCREW M8', 'GRUBM5X20' -> 'GRUB M5X20'.
    """
    return re.sub(rf"(?<=[A-Z])(?={_UNIT_PREFIXES}\d)", " ", text)


# -------------------------------------------------------
# Model / part number extraction (compound codes kept fused)
# -------------------------------------------------------
def extract_model_numbers(text: str) -> str:
    """Extract dash/slash-joined and alnum part-numbers as standalone tokens.

    Returns a space-joined, deduped, lowercased string of extracted codes.
    Compound codes (e.g. 'WDS500-G2B0A', '4H-210-08') are kept intact since
    splitting them destroys the exact identifier. Bare alnum runs are only
    kept if they mix letters+digits and are long enough to be a real code
    (avoids false positives like 'kg', 'x1').
    """
    if pd.isna(text):
        return ""

    text = str(text).upper()
    codes = []

    # 1. dash/slash joined compound part numbers - keep fused, pull out first
    compound_pattern = r"\b[A-Z0-9]+(?:[-/][A-Z0-9]+)+\b"
    for m in re.finditer(compound_pattern, text):
        codes.append(m.group())
    remainder = re.sub(compound_pattern, " ", text)

    # 2. split a unit-prefix+digit run off a preceding word (SCREWM8 -> SCREW M8)
    remainder = _insert_unit_prefix_boundary(remainder)

    # 3. any remaining non-alnum/dash/slash char (*, comma, parens, etc.) is a
    #    hard token boundary - turn into whitespace, don't just delete it,
    #    otherwise "M8*20" collapses into the bogus code "M820"
    remainder = re.sub(r"[^A-Z0-9/\-\s]", " ", remainder)

    for tok in remainder.split():
        tok_clean = tok.strip("-/")
        if len(tok_clean) < 2:
            continue
        has_alpha = any(c.isalpha() for c in tok_clean)
        has_digit = any(c.isdigit() for c in tok_clean)
        if has_alpha and has_digit:
            codes.append(tok_clean)

    seen = set()
    out = []
    for c in codes:
        c = c.lower()
        if c not in seen:
            out.append(c)
            seen.add(c)
    return " ".join(out)


# -------------------------------------------------------
# General text cleaning (shared)
# -------------------------------------------------------
def _split_alnum_boundaries(text: str) -> str:
    """Insert spaces at letter<->digit boundaries so dimension tokens like
    'm8', '20mm' surface as standalone tokens instead of staying fused to
    neighbouring words. Unit-prefix aware first (screwm8 -> screw m8), then
    a general letter<->digit split for anything left over."""
    text = _insert_unit_prefix_boundary(text.upper()).lower()
    return text


def clean_general_text(text: str, split_alnum: bool = True) -> str:
    """Lowercase, strip ERP boilerplate, sanitize characters, split alnum
    boundaries, drop stop words, dedupe while preserving order."""
    if pd.isna(text):
        return ""

    text = str(text).lower()

    # Strip ERP export artifacts. "_x000d_" is the literal escaped-CR marker
    # some ERP/Excel exports leave behind in place of real newlines (see
    # row 0 of Remarks.xlsx - "120MM2\r\r\r\n16MM" survived as raw
    # "_x000d_" tokens and fragmented "120mm2" downstream). Strip before
    # anything else touches whitespace.
    text = re.sub(r"_x000d_", " ", text, flags=re.IGNORECASE)

    # Normalize the handful of unit spellings that show up interchangeably
    # in ERP free text vs. the base material master ("sq.mm"/"sq mm"/"sqmm"
    # all mean the same thing, but only one survives the sanitizer's
    # allow-listed '.' character unmolested and the others don't match it).
    # Add more pairs here as eval runs surface them.
    text = re.sub(r"\bsq\.?\s*mm\b", "sqmm", text)
    text = re.sub(r"\bsq\.?\s*cm\b", "sqcm", text)

    # Strip common ERP prefixes / trailing reference numbers
    text = re.sub(r"item\s*code\s*[:-]?", " ", text)
    text = re.sub(r"product\s*code\s*[:-]?", " ", text)
    text = re.sub(r"po\s*no\.?\s*[:-]?\s*\S+", " ", text)
    text = re.sub(r"invoice\s*no\.?\s*[:-]?\s*\S+", " ", text)
    text = re.sub(r"imei\s*no\.?\s*[:-]?\s*\S+", " ", text)
    text = re.sub(r"serial\s*no\.?\s*[:-]?\s*\S+", " ", text)

    # Sanitize: keep engineering symbols, drop everything else
    text = re.sub(r"[^a-z0-9./x+\- ]+", " ", text)

    if split_alnum:
        text = _split_alnum_boundaries(text)

    text = re.sub(r"\s+", " ", text).strip()

    tokens = [
        t for t in text.split()
        if t not in STOP_WORDS and not re.fullmatch(r"[.\-/x+]+", t)
    ]

    seen = set()
    cleaned = []
    for t in tokens:
        if t not in seen:
            cleaned.append(t)
            seen.add(t)
    return " ".join(cleaned)


def dehyphenate_model_numbers(model_numbers: str) -> str:
    """Given the space-joined output of extract_model_numbers, return the
    same codes with internal dashes/slashes stripped, e.g. 'b-52' -> 'b52'.

    Why this exists: the compound-code branch of extract_model_numbers
    deliberately keeps a code like 'B-52' fused WITH its dash so an exact
    identifier like 'WDS500-G2B0A' isn't destroyed. But ERP query text
    often types a hyphen ("B-52", "55-75-10") where the underlying
    productSpecification never had one to begin with ("part b52",
    "55x75x10") - so the query-side and index-side codes diverge on a
    character that carries no real signal here. Rather than guess which
    codes "should" keep their dash, generate the stripped form as an
    additional exact-match candidate and let the search try both.
    """
    if not model_numbers:
        return ""
    stripped = [tok.replace("-", "").replace("/", "") for tok in model_numbers.split()]
    seen = set()
    out = []
    for tok in stripped:
        if tok and tok not in seen:
            out.append(tok)
            seen.add(tok)
    return " ".join(out)


def clean_and_extract(raw_text: str) -> dict:
    """One entry point used identically by index-side and query-side code.

    Returns {'general_text': ..., 'model_numbers': ...}
    """
    model_numbers = extract_model_numbers(raw_text)
    general_text = clean_general_text(raw_text, split_alnum=True)
    return {"general_text": general_text, "model_numbers": model_numbers}
