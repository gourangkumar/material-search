"""
index_data_merged.py
--------------------------------------------------------------------------
Merge of index_data.py + index_data_sai.py.

Diff between the two originals:

  1. mat_qty required/converted (sai) vs commented out entirely (base).
     Kept as a toggle (MAT_QTY_REQUIRED below) so this script stays in
     sync with whichever schema create_collection_merged.py actually
     created - set both to the same value. Defaults to True to match
     create_collection_merged.py's default.

  2. dirty_values: "coerce_or_drop" added to the import options (sai).
     Pure improvement, no toggle needed: without it, a single row with a
     type mismatch (e.g. a stray non-numeric materialId that slipped past
     the pd.to_numeric coercion upstream) can fail that row outright
     instead of Typesense coercing or dropping just the offending field.
     Kept unconditionally.

  3. Failure logging (sai) vs none (base). base only counted failures;
     sai captures (materialId, error) for each failed row and logs a
     sample. This is strictly more useful for debugging a bad indexing
     run and has no downside, so it's kept unconditionally, plus a small
     addition: batch progress is now logged as "batch N/total" (the
     total_batches value existed in both originals but was never actually
     used in either).
--------------------------------------------------------------------------
"""

import os
import time
import logging
import pandas as pd

# NOTE: adjust this import path if your project's package layout differs -
# this mirrors the "scripts.create_collection" import the two originals used.
from scripts.create_collection_merged import get_typesense_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Keep this in sync with create_collection_merged.py's USE_MAT_QTY_SORT -
# both scripts need to agree on whether mat_qty is part of the schema/data.
MAT_QTY_REQUIRED = True


def index_data(csv_path: str, collection_name: str, batch_size: int = 5000, action: str = "upsert"):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"{csv_path} not found.")

    client = get_typesense_client()
    logging.info(f"Reading {csv_path} for collection '{collection_name}'...")
    df = pd.read_csv(csv_path)

    required_columns = [
        "materialId", "categoryName", "brandName", "productName",
        "productSpecification", "modelNumbers", "generalText",
    ]
    if MAT_QTY_REQUIRED:
        required_columns.append("mat_qty")

    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["materialId"] = pd.to_numeric(df["materialId"], errors="coerce").fillna(0).astype(int)
    if MAT_QTY_REQUIRED:
        df["mat_qty"] = pd.to_numeric(df["mat_qty"], errors="coerce").fillna(0).astype(int)

    text_cols = ["categoryName", "brandName", "productName", "productSpecification", "modelNumbers", "generalText"]
    for col in text_cols:
        df[col] = df[col].fillna("").astype(str)

    df["id"] = df["materialId"].astype(str)
    documents = df.to_dict("records")
    total_docs = len(documents)
    total_batches = (total_docs + batch_size - 1) // batch_size

    logging.info(f"Indexing {total_docs:,} documents into '{collection_name}'...")
    start = time.perf_counter()
    success, failed = 0, 0

    for batch_no, start_idx in enumerate(range(0, total_docs, batch_size), start=1):
        batch = documents[start_idx:start_idx + batch_size]
        retries = 3
        while retries:
            try:
                results = client.collections[collection_name].documents.import_(
                    batch, {"action": action, "dirty_values": "coerce_or_drop"}
                )
                batch_failed = [
                    (batch[i].get("materialId"), r.get("error"))
                    for i, r in enumerate(results) if not r.get("success", False)
                ]
                success += len(batch) - len(batch_failed)
                failed += len(batch_failed)
                if batch_failed:
                    logging.warning(
                        f"Batch {batch_no}/{total_batches}: {len(batch_failed)} rows failed: {batch_failed[:10]}"
                    )
                else:
                    logging.info(f"Batch {batch_no}/{total_batches}: {len(batch)} rows imported.")
                break
            except Exception as e:
                retries -= 1
                if retries == 0:
                    logging.error(f"Batch {batch_no}/{total_batches} failed permanently: {e}")
                    failed += len(batch)
                else:
                    time.sleep(2)

    elapsed = time.perf_counter() - start
    logging.info(f"Finished indexing '{collection_name}' in {elapsed:.1f}s | Imported: {success:,} | Failed: {failed:,}")


if __name__ == "__main__":
    index_data(os.path.join("data", "materials_master.csv"), "materials_master")
    index_data(os.path.join("data", "materials_temp.csv"), "materials_temp")
