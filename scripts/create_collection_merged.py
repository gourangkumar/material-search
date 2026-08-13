"""
create_collection_merged.py
--------------------------------------------------------------------------
Merge of create_collection.py + create_collection_sai.py.

Diff between the two originals was two changes, both improvements in
create_collection_sai.py with no offsetting downside in create_collection.py:

  1. modelNumbers gets infix=True (sai) vs no infix (base).
     Improvement: ERP part numbers are frequently compound ("ABC-4521-X")
     and procurement users often search on just the numeric segment.
     Typesense's default tokenizer already splits on the hyphen, so
     "4521" matches as its own token for well-formed data - infix is a
     safety net for the messier case where a code is glued together with
     no separator at all ("ABC4521X"). Kept as a toggle below (
     MODEL_NUMBERS_INFIX) because infix search always runs once enabled
     on this Typesense server version (boolean, not the "fallback" mode
     some newer versions support) - so it's a real query-latency
     trade-off you may want to switch off if this field gets slow.

  2. mat_qty field + default_sorting_field=mat_qty (sai) vs no mat_qty
     field + default_sorting_field=materialId (base).
     Improvement: mat_qty (recent 6-month requirement volume, computed in
     preprocess.py) as the default sort means Typesense's tie-breaking
     for equal text_match scores favors materials that are actually
     being bought, instead of an arbitrary materialId ordering. Kept as
     a toggle (USE_MAT_QTY_SORT) since it requires preprocess.py/
     preprocess_merged.py to actually populate mat_qty - if you point
     this at a CSV that doesn't have it, flip this off rather than
     letting collection creation fail on a missing default_sorting_field.

Both toggles default to the sai behavior (True) since that's the more
recent, evaluation-driven version - flip them off individually if you
need to fall back to the simpler base behavior for either.
--------------------------------------------------------------------------
"""

import logging
import typesense
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -------------------------------------------------------
# Toggles - see module docstring for the trade-off each one encodes.
# -------------------------------------------------------
MODEL_NUMBERS_INFIX = True
USE_MAT_QTY_SORT = False


def get_typesense_client():
    return typesense.Client({
        'nodes': [{
            'host': config.TYPESENSE_HOST,
            'port': str(config.TYPESENSE_PORT),
            'protocol': config.TYPESENSE_PROTOCOL
        }],
        'api_key': config.TYPESENSE_API_KEY,
        'connection_timeout_seconds': 5
    })


def create_single_collection(client, collection_name: str, force_recreate: bool = True):
    if force_recreate:
        try:
            client.collections[collection_name].delete()
            logging.info(f"Deleted existing collection '{collection_name}'.")
        except Exception as e:
            logging.warning(f"Could not delete collection '{collection_name}': {e}")

    # NOTE on the change from the pre-both-variants schema:
    # The old approach concatenated brandName x3 + productName x2 + spec +
    # modelNumbers x2 + categoryName into a single "searchText" field and
    # queried only that field. That bakes relative field importance into
    # string repetition, which is hard to tune and (per the eval data)
    # over-weights brand vs. dimension/spec tokens.
    #
    # Instead we keep fields separate and control relative importance at
    # QUERY time via query_by_weights (see evaluate_search*.py). This also
    # lets us add a dedicated modelNumbers field that gets its own typo
    # tolerance (part numbers should not fuzzy-match as loosely as prose).
    model_numbers_field = {"name": "modelNumbers", "type": "string", "optional": True}
    if MODEL_NUMBERS_INFIX:
        model_numbers_field["infix"] = True

    fields = [
        {"name": "materialId", "type": "int64", "sort": True},
        {"name": "categoryName", "type": "string", "facet": True, "optional": True},
        {"name": "brandName", "type": "string", "facet": True, "optional": True},
        {"name": "productName", "type": "string", "optional": True},
        {"name": "productSpecification", "type": "string", "optional": True},
        model_numbers_field,
        {"name": "generalText", "type": "string", "optional": True},
    ]

    if USE_MAT_QTY_SORT:
        fields.append({"name": "mat_qty", "type": "int32", "sort": True})

    schema = {
        "name": collection_name,
        "fields": fields,
        "default_sorting_field": "mat_qty" if USE_MAT_QTY_SORT else "materialId",
    }

    try:
        client.collections.create(schema)
        logging.info(f"Collection '{collection_name}' created successfully.")
    except Exception as e:
        logging.error(f"Failed to create collection '{collection_name}': {e}")
        raise e


def create_materials_collections(force_recreate: bool = True):
    client = get_typesense_client()
    create_single_collection(client, "materials_master", force_recreate)
    create_single_collection(client, "materials_temp", force_recreate)


if __name__ == "__main__":
    create_materials_collections(force_recreate=True)
