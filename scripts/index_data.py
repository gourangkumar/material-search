import os
import time
import logging
import pandas as pd

# NOTE: adjust this import path if your project's package layout differs -
# this mirrors the "scripts.create_collection" import the two originals used.
try:
    from .create_collection import get_typesense_client
except ImportError:
    from create_collection import get_typesense_client

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
        "productSpecification", "modelNumbers", "generalText", "generalTextNormalized",
        "brandNameNormalized", "companyERPCode", "companyERPCodeNormalized",
    ]
    if MAT_QTY_REQUIRED:
        required_columns.append("mat_qty")

    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["materialId"] = pd.to_numeric(df["materialId"], errors="coerce").fillna(0).astype(int)
    if MAT_QTY_REQUIRED:
        df["mat_qty"] = pd.to_numeric(df["mat_qty"], errors="coerce").fillna(0).astype(int)

    text_cols = [
        "categoryName", "brandName", "brandNameNormalized", "productName",
        "productSpecification", "modelNumbers", "generalText",
        "generalTextNormalized", "companyERPCode", "companyERPCodeNormalized",
    ]
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
