"""
preprocess_merged.py
--------------------------------------------------------------------------
Merge of preprocess.py + preprocess_sai.py.

Diff between the two originals:

  1. normalize_number_unit_spacing() (sai only).
     evaluate_search.py's / evaluate_search_latest_new.py's number_unit
     tier queries productSpecification for the FUSED form ("20mm") with
     num_typos=0. Typesense tokenizes on whitespace, so a document whose
     source ERP data has the SPACED form ("20 mm") is indexed as two
     separate tokens and that tier will never match it - the query-side
     variant expansion has no index-side counterpart without this. This
     is a genuine correctness fix (not a stylistic difference), so it's
     kept unconditionally, applied to productSpecification BEFORE
     modelNumbers/generalText are derived so both inherit the dual forms.

     One change from preprocess_sai.py: the unit-word list here is widened
     to the UNION of every evaluate_search*.py variant's list, not just
     evaluate_search.py's original 20-word set. evaluate_search_latest_new.py
     independently added "gms", "gsm", "sqcm" and preprocess_sai.py's
     comment ("must stay in sync ... if you add a unit there, add it
     here too") was never updated for that. Since evaluate_search_merged.py
     runs all variants together, the index-side normalization should
     cover the superset of what any of them might query for.

  2. Row sort order before writing the CSV: base sorts by
     (mat_qty desc, materialId desc); sai skips sorting (writes natural
     DB row order). This has NO effect on search quality - Typesense
     doesn't care about input row order, ranking is entirely driven by
     text_match plus default_sorting_field at query time (see
     create_collection_merged.py). It only affects how the CSV reads when
     eyeballed for QA. Kept as a toggle (SORT_OUTPUT) defaulting to True
     since deterministic, popularity-ordered output is more convenient to
     spot-check and diff between preprocessing runs; flip off if you'd
     rather match raw DB order for some other reason.
--------------------------------------------------------------------------
"""

import os
import re
import logging
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

from text_utils import extract_model_numbers, clean_general_text

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -------------------------------------------------------
# Toggle - see point 2 in the module docstring. Cosmetic only.
# -------------------------------------------------------
SORT_OUTPUT = True

# -------------------------------------------------------
# Union of unit words across ALL evaluate_search*.py variants (base +
# latest_new's extras: gms, gsm, sqcm). Must stay in sync with the widest
# _UNIT_WORDS set among the evaluate_search*.py scripts - if you add a
# unit to any of them, add it here too, since evaluate_search_merged.py
# runs every variant against this index.
# -------------------------------------------------------
_UNIT_WORDS = {
    "mm", "cm", "kg", "gm", "gms", "gsm", "ml", "ltr", "kw", "hp", "rpm",
    "amp", "kv", "v", "w", "inch", "pin", "sqmm", "sqcm", "sq", "core",
    "phase", "m",
}
_UNIT_WORDS_PATTERN = "|".join(sorted(_UNIT_WORDS, key=len, reverse=True))
_NUM_UNIT_SPACED_RE = re.compile(
    rf'\b(\d+(?:\.\d+)?)\s+({_UNIT_WORDS_PATTERN})\b', re.IGNORECASE
)
_NUM_UNIT_FUSED_RE = re.compile(
    rf'\b(\d+(?:\.\d+)?)({_UNIT_WORDS_PATTERN})\b', re.IGNORECASE
)


def normalize_number_unit_spacing(text: str) -> str:
    """Appends the 'other' spacing form for every number+unit occurrence
    found, so the indexed text contains BOTH tokenizations ('20mm' AND
    '20 mm') regardless of which one the source ERP data happened to use.
    Appending rather than replacing keeps this safe for a bag-of-tokens
    field - duplicate tokens don't hurt Typesense's text_match scoring in
    any meaningful way, they just guarantee a match exists."""
    if not text:
        return text
    additions = [
        f"{m.group(1)}{m.group(2)}" for m in _NUM_UNIT_SPACED_RE.finditer(text)
    ] + [
        f"{m.group(1)} {m.group(2)}" for m in _NUM_UNIT_FUSED_RE.finditer(text)
    ]
    return f"{text} {' '.join(additions)}" if additions else text


# Helper function to generate query for a specific table
def get_materials_query(table_name: str) -> str:
    return f"""
    WITH filtered_materials AS (
        SELECT
            "materialId",
            "brandId",
            "categoryId",
            "productName",
            "productSpecification"
        FROM "{table_name}"
    ),
    recent_requirements AS (
        SELECT
            bri."materialId",
            SUM(bri.qty) AS req_count
        FROM "buyerReqItem" bri
        WHERE bri."createdAt" >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months'
        GROUP BY bri."materialId"
    )
    SELECT
        m."materialId",
        COALESCE(mc."categoryName", '') AS "categoryName",
        COALESCE(mb."brandName", '') AS "brandName",
        COALESCE(m."productName", '') AS "productName",
        COALESCE(m."productSpecification", '') AS "productSpecification",
        COALESCE(r.req_count, 0) AS mat_qty
    FROM filtered_materials m
    LEFT JOIN "materialBrands" mb ON mb."brandId" = m."brandId"
    LEFT JOIN "materialCategories" mc ON mc."categoryId" = m."categoryId"
    LEFT JOIN recent_requirements r ON r."materialId" = m."materialId";
    """


# ---------------------------------------------------------
# Main preprocessing procedure per table
# ---------------------------------------------------------
def preprocess_table(engine, table_name: str, output_csv_path: str):
    logging.info(f"Fetching raw data for '{table_name}'...")
    query = get_materials_query(table_name)
    df = pd.read_sql(query, con=engine)

    df["materialId"] = pd.to_numeric(df["materialId"], errors="coerce").fillna(0).astype(int)
    df["mat_qty"] = pd.to_numeric(df["mat_qty"], errors="coerce").fillna(0).astype(int)

    string_cols = ["categoryName", "brandName", "productName", "productSpecification"]
    for col in string_cols:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # Must happen before modelNumbers/generalText are built below, since
    # both are derived from this column and should inherit the dual
    # spacing forms too.
    df["productSpecification"] = df["productSpecification"].apply(normalize_number_unit_spacing)

    # Model / part numbers pulled from BOTH productName and productSpecification,
    # using the exact same extractor the query side uses (text_utils.extract_model_numbers).
    combined_for_models = df["productName"].fillna("") + " " + df["productSpecification"].fillna("")
    df["modelNumbers"] = combined_for_models.apply(extract_model_numbers)

    # General free-text field: brand + product name + spec + category, cleaned
    # with the SAME pipeline the query side uses (no repetition weighting -
    # relative field importance is controlled at query time via query_by_weights).
    combined_for_general = (
        df["brandName"] + " "
        + df["productName"] + " "
        + df["productSpecification"] + " "
        + df["categoryName"]
    )
    df["generalText"] = combined_for_general.apply(clean_general_text)

    if SORT_OUTPUT:
        df = df.sort_values(by=["mat_qty", "materialId"], ascending=[False, False]).reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    df.to_csv(output_csv_path, index=False)
    logging.info(f"Saved {len(df)} records from {table_name} to {output_csv_path}")


if __name__ == "__main__":
    DB_URL = os.getenv("DATABASE_URL")
    if not DB_URL:
        raise ValueError("DATABASE_URL not found in .env file")

    db_engine = create_engine(DB_URL)

    # Process both tables into separate files
    preprocess_table(db_engine, "materialMaster", os.path.join("data", "materials_master.csv"))
    preprocess_table(db_engine, "materialMasterTemp", os.path.join("data", "materials_temp.csv"))
