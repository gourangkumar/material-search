import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd
from config import config

from text_utils import clean_general_text, extract_model_numbers, dehyphenate_model_numbers

# -------------------------------------------------------
# Logging Configuration
# -------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -------------------------------------------------------
# Typesense & File Configurations
# -------------------------------------------------------
TYPESENSE_URL = (
    f"{config.TYPESENSE_PROTOCOL}://"
    f"{config.TYPESENSE_HOST}:"
    f"{config.TYPESENSE_PORT}/multi_search"
)

HEADERS = {
    "X-TYPESENSE-API-KEY": config.TYPESENSE_API_KEY,
    "Content-Type": "application/json"
}

PRIMARY_COLLECTION = "materials_master"
TEMP_COLLECTION = "materials_temp"

INPUT_FILE = "data/eval_queries.csv"
OUTPUT_FILE = "data/search_results.csv"

BATCH_SIZE = 25
CONCURRENCY_LIMIT = 5

# Priority order of scripts
SCRIPT_PIPELINES = [
    "evaluate_search_latest",
    "evaluate_search_sai",
    "evaluate_search_latest_new",
    "evaluate_search"
]

TOP_K = 5
TIER_POOL_SIZE = 15

# Global Text / Match Configurations
_DIM_RE = re.compile(r'\b(\d+(?:\.\d+)?(?:/\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?(?:/\d+)?)\b')
_DIM_CHAIN_RE = re.compile(r'\b(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\b')
_UNIT_WORDS = {
    "mm", "cm", "kg", "gm", "gms", "gsm", "ml", "ltr", "kw", "hp", "rpm",
    "amp", "kv", "v", "w", "inch", "pin", "sqmm", "sqcm", "sq", "core",
    "phase", "m",
}
_UNIT_WORDS_PATTERN = "|".join(sorted(_UNIT_WORDS, key=len, reverse=True))
_NUM_UNIT_RE = re.compile(rf'(\d+(?:\.\d+)?)\s*({_UNIT_WORDS_PATTERN})\b', re.IGNORECASE)

SYMMETRIC_SYNONYMS = [
    ("screw driver", "screwdriver"),
    ("core", "cores"),
    ("cable", "cables"),
    ("v belt", "v-belt"),
    ("tecno", "techno")
]

# -------------------------------------------------------
# Script Configurations Registry
# -------------------------------------------------------
SCRIPT_CONFIGS = {
    "evaluate_search_latest": {
        "QUERY_BY": "modelNumbers,brandName,productName,productSpecification,generalText",
        "QUERY_BY_WEIGHTS": "3,1,1,2,6",
        "NUM_TYPOS": "1,1,2,2,2",
        "has_dehyphenated": True,
        "has_dim_chain": True,
        "has_number_unit": True,
        "pool_size": TIER_POOL_SIZE
    },
    "evaluate_search_sai": {
        "QUERY_BY": "modelNumbers,brandName,productName,productSpecification,categoryName,generalText",
        "QUERY_BY_WEIGHTS": "3,1,1,2,1,6",
        "NUM_TYPOS": "1,1,2,2,1,2",
        "has_dehyphenated": False,
        "has_dim_chain": False,
        "has_number_unit": True,
        "pool_size": TIER_POOL_SIZE
    },
    "evaluate_search_latest_new": {
        "QUERY_BY": "modelNumbers,brandName,productName,productSpecification,categoryName,generalText",
        "QUERY_BY_WEIGHTS": "3,1,1,2,1,6",
        "NUM_TYPOS": "1,1,2,2,1,2",
        "has_dehyphenated": False,
        "has_dim_chain": False,
        "has_number_unit": False,
        "pool_size": TOP_K
    },
    "evaluate_search": {
        "QUERY_BY": "modelNumbers,brandName,productName,productSpecification,categoryName,generalText",
        "QUERY_BY_WEIGHTS": "1,1,1,2,1,6",
        "NUM_TYPOS": "1,1,2,2,1,2",
        "has_dehyphenated": False,
        "has_dim_chain": False,
        "has_number_unit": False,
        "pool_size": TOP_K
    }
}


# -------------------------------------------------------
# Query Variant Generators
# -------------------------------------------------------
def extract_number_units(text: str) -> List[Tuple[str, str]]:
    return [(m.group(1), m.group(2).lower()) for m in _NUM_UNIT_RE.finditer(text)]


def _dimension_variants(text: str) -> List[str]:
    if not _DIM_RE.search(text):
        return []
    fused = _DIM_RE.sub(lambda m: f"{m.group(1)}x{m.group(2)}", text)
    spaced = _DIM_RE.sub(lambda m: f"{m.group(1)} x {m.group(2)}", text)
    out = []
    for v in (fused, spaced):
        if v != text and v not in out:
            out.append(v)
    return out


def _dimension_chain_variants(text: str) -> List[str]:
    if not _DIM_CHAIN_RE.search(text):
        return []
    xed = _DIM_CHAIN_RE.sub(lambda m: f"{m.group(1)}x{m.group(2)}x{m.group(3)}", text)
    return [xed] if xed != text else []


def _unit_spacing_variants(text: str) -> List[str]:
    spaced = re.sub(rf'(\d+(?:\.\d+)?)({_UNIT_WORDS_PATTERN})\b', r'\1 \2', text, flags=re.IGNORECASE)
    fused = re.sub(rf'(\d+(?:\.\d+)?)\s+({_UNIT_WORDS_PATTERN})\b', r'\1\2', text, flags=re.IGNORECASE)
    out = []
    for v in (spaced, fused):
        if v != text and v not in out:
            out.append(v)
    return out


def _synonym_variants(text: str) -> List[str]:
    out = []
    for a, b in SYMMETRIC_SYNONYMS:
        if a in text:
            v = text.replace(a, b)
            if v not in out:
                out.append(v)
        if b in text:
            v = text.replace(b, a)
            if v not in out:
                out.append(v)
    return out


def expand_query_variants(cleaned_query: str, include_dim_chain: bool = False, max_variants: int = 4) -> List[str]:
    variants = [cleaned_query]
    generators = [_dimension_variants]
    if include_dim_chain:
        generators.append(_dimension_chain_variants)
    generators.extend([_unit_spacing_variants, _synonym_variants])

    for fn in generators:
        for v in fn(cleaned_query):
            if v not in variants:
                variants.append(v)
        if len(variants) >= max_variants:
            break
    return variants[:max_variants]


def build_query_plan(raw_text: Any) -> Dict[str, Any]:
    cleaned = clean_general_text(raw_text)
    model_numbers = extract_model_numbers(raw_text)
    full_query = f"{cleaned} {model_numbers}".strip() if model_numbers else cleaned
    
    variants_std = expand_query_variants(full_query, include_dim_chain=False)
    variants_chain = expand_query_variants(full_query, include_dim_chain=True)

    model_numbers_dehyphenated = dehyphenate_model_numbers(model_numbers)

    def sanitize_variants(v_list):
        v_list = [v for v in v_list if v.strip()]
        if not v_list:
            raw_fallback = str(raw_text).strip() if not pd.isna(raw_text) else ""
            v_list = [raw_fallback] if raw_fallback else ["*"]
        return v_list

    return {
        "cleaned_query": cleaned,
        "model_numbers": model_numbers,
        "model_numbers_dehyphenated": model_numbers_dehyphenated,
        "variants_std": sanitize_variants(variants_std),
        "variants_chain": sanitize_variants(variants_chain),
    }


# -------------------------------------------------------
# Typesense Helpers
# -------------------------------------------------------
def build_search_param(collection: str, query: str, cfg: dict, per_page: int) -> Dict[str, Any]:
    payload = {
        "collection": collection,
        "q": query,
        "query_by": cfg["QUERY_BY"],
        "query_by_weights": cfg["QUERY_BY_WEIGHTS"],
        "num_typos": cfg["NUM_TYPOS"],
        "per_page": per_page,
        "prefix": False,
        "drop_tokens_threshold": 1,
        "typo_tokens_threshold": 2,
        "prioritize_num_matching_fields": True,
        "include_fields": "materialId,brandName,productName,productSpecification"
    }
    if cfg["has_dehyphenated"]:
        payload["text_match_type"] = "sum_score"
    return payload


def build_exact_model_search_param(collection: str, model_numbers: str, cfg: dict, per_page: int) -> Dict[str, Any]:
    payload = {
        "collection": collection,
        "q": model_numbers,
        "query_by": "modelNumbers",
        "num_typos": "0",
        "prefix": False,
        "per_page": per_page,
        "include_fields": "materialId,brandName,productName,productSpecification"
    }
    if cfg.get("pool_size", 5) == TIER_POOL_SIZE:
        payload["infix"] = "fallback"
    return payload


def build_number_unit_search_param(collection: str, cleaned_query: str, per_page: int) -> Optional[Dict[str, Any]]:
    pairs = extract_number_units(cleaned_query)
    if not pairs:
        return None
    phrase = " ".join(f"{n}{u}" for n, u in pairs)
    return {
        "collection": collection,
        "q": phrase,
        "query_by": "productSpecification",
        "num_typos": "0",
        "prefix": False,
        "per_page": per_page,
        "include_fields": "materialId,brandName,productName,productSpecification"
    }


MAX_SEARCHES_PER_REQUEST = 20


async def _run_multi_search(
    http_client: httpx.AsyncClient,
    searches: List[Dict[str, Any]],
    batch_idx: int,
) -> List[Dict[str, Any]]:
    if not searches:
        return []

    chunks = [
        searches[i:i + MAX_SEARCHES_PER_REQUEST]
        for i in range(0, len(searches), MAX_SEARCHES_PER_REQUEST)
    ]

    all_results: List[Dict[str, Any]] = []
    for chunk in chunks:
        response = await http_client.post(
            TYPESENSE_URL,
            json={"searches": chunk},
            headers=HEADERS,
            timeout=30.0
        )
        response.raise_for_status()
        all_results.extend(response.json().get("results", []))

    return all_results


def _hit_to_doc(hit: Dict[str, Any]) -> Dict[str, Any]:
    doc = hit["document"]
    return {
        "materialId": doc.get("materialId"),
        "brandName": doc.get("brandName"),
        "productName": doc.get("productName"),
        "productSpecification": doc.get("productSpecification"),
        "score": hit.get("text_match"),
    }


# -------------------------------------------------------
# Parallel Script Pipeline Engine
# -------------------------------------------------------
async def execute_script_pipeline(
    script_name: str,
    http_client: httpx.AsyncClient,
    batch_idx: int,
    batch_plans: List[Dict[str, Any]]
) -> List[List[Dict[str, Any]]]:
    cfg = SCRIPT_CONFIGS[script_name]
    pool_size = cfg["pool_size"]

    searches: List[Dict[str, Any]] = []
    spec_map: List[List[Tuple[str, int]]] = []

    for plan in batch_plans:
        entries: List[Tuple[str, int]] = []
        
        # 1. Exact Model Tier
        if plan["model_numbers"]:
            entries.append(("exact_model", len(searches)))
            searches.append(build_exact_model_search_param(PRIMARY_COLLECTION, plan["model_numbers"], cfg, pool_size))
            
            if cfg["has_dehyphenated"]:
                dehy = plan["model_numbers_dehyphenated"]
                if dehy and dehy != plan["model_numbers"]:
                    entries.append(("exact_model", len(searches)))
                    searches.append(build_exact_model_search_param(PRIMARY_COLLECTION, dehy, cfg, pool_size))

        # 2. Number-Unit Tier
        if cfg["has_number_unit"]:
            nu_param = build_number_unit_search_param(PRIMARY_COLLECTION, plan["cleaned_query"], pool_size)
            if nu_param is not None:
                entries.append(("number_unit", len(searches)))
                searches.append(nu_param)

        # 3. Variant Expansion Tier
        variants = plan["variants_chain"] if cfg["has_dim_chain"] else plan["variants_std"]
        for variant in variants:
            entries.append(("variant", len(searches)))
            searches.append(build_search_param(PRIMARY_COLLECTION, variant, cfg, pool_size))

        spec_map.append(entries)

    results_raw = await _run_multi_search(http_client, searches, batch_idx)

    # Merge Hits
    pipeline_results: List[List[Dict[str, Any]]] = []
    fallback_positions: List[int] = []

    for i, entries in enumerate(spec_map):
        merged: Dict[Any, Tuple[int, Any, Dict[str, Any]]] = {}
        variant_mids: set = set()
        deferred_number_unit: List[Tuple[int, Dict[str, Any]]] = []

        for kind, pos in entries:
            result = results_raw[pos] if pos < len(results_raw) else {}
            
            if kind == "number_unit" and cfg["has_dehyphenated"]:
                deferred_number_unit.append((pos, result))
                continue

            priority = 2 if kind == "exact_model" else (1 if kind == "number_unit" else 0)
            for hit in result.get("hits", []):
                doc = _hit_to_doc(hit)
                mid = doc["materialId"]
                if mid is None:
                    continue
                if kind == "variant":
                    variant_mids.add(mid)
                score = doc["score"] or 0
                current = merged.get(mid)
                if current is None or (priority, score) > (current[0], current[1]):
                    merged[mid] = (priority, score, doc)

        if deferred_number_unit:
            for _, result in deferred_number_unit:
                for hit in result.get("hits", []):
                    doc = _hit_to_doc(hit)
                    mid = doc["materialId"]
                    if mid is None:
                        continue
                    corroborated = mid in variant_mids
                    priority = 1 if corroborated else 0
                    score = doc["score"] or 0
                    current = merged.get(mid)
                    if current is None or (priority, score) > (current[0], current[1]):
                        merged[mid] = (priority, score, doc)

        ranked = sorted(merged.values(), key=lambda t: (t[0], t[1]), reverse=True)
        docs = [d for _, _, d in ranked][:TOP_K]
        pipeline_results.append(docs)
        if len(docs) < TOP_K:
            fallback_positions.append(i)

    # Fallback Execution
    if fallback_positions:
        fallback_searches = [
            build_search_param(
                TEMP_COLLECTION,
                (plan["variants_chain"] if cfg["has_dim_chain"] else plan["variants_std"])[0],
                cfg,
                TOP_K - len(pipeline_results[i])
            )
            for i, plan in enumerate(batch_plans) if i in fallback_positions
        ]

        fallback_results = await _run_multi_search(http_client, fallback_searches, batch_idx)

        for pos, result in enumerate(fallback_results):
            target_index = fallback_positions[pos]
            existing_ids = {d["materialId"] for d in pipeline_results[target_index]}
            for hit in result.get("hits", []):
                doc = _hit_to_doc(hit)
                if doc["materialId"] in existing_ids:
                    continue
                pipeline_results[target_index].append(doc)
                existing_ids.add(doc["materialId"])

    return pipeline_results


async def process_batch_merged(
    sem: asyncio.Semaphore,
    http_client: httpx.AsyncClient,
    batch_idx: int,
    batch_plans: List[Dict[str, Any]],
    target_material_ids: List[Any],
    max_retries: int = 3
) -> Tuple[int, List[Dict[str, Any]]]:

    async with sem:
        for attempt in range(max_retries):
            try:
                # Execute all 4 script logic variations concurrently
                script_tasks = [
                    execute_script_pipeline(s_name, http_client, batch_idx, batch_plans)
                    for s_name in SCRIPT_PIPELINES
                ]
                pipeline_outputs = await asyncio.gather(*script_tasks)

                # pipeline_outputs[script_index][query_index] -> List[Dict]
                batch_final_results: List[Dict[str, Any]] = []

                for q_idx in range(len(batch_plans)):
                    target_id = target_material_ids[q_idx]
                    matched_script_idx = None
                    matched_rank = None
                    selected_results = None

                    # Check script outputs in order: evaluate_search_latest -> sai -> latest_new -> search
                    for s_idx, s_output in enumerate(pipeline_outputs):
                        query_hits = s_output[q_idx]
                        
                        # Search for materialId match in the 5 returned candidates
                        if pd.notna(target_id):
                            for rank_idx, doc in enumerate(query_hits):
                                if str(doc["materialId"]) == str(target_id):
                                    matched_script_idx = s_idx
                                    matched_rank = rank_idx + 1
                                    selected_results = query_hits
                                    break
                        
                        if matched_script_idx is not None:
                            break

                    # Fallback if no match across all scripts: pick evaluate_search_latest output
                    if selected_results is None:
                        selected_results = pipeline_outputs[0][q_idx]
                        matched_rank = None

                    batch_final_results.append({
                        "results": selected_results,
                        "matched_rank": matched_rank
                    })

                return batch_idx, batch_final_results

            except Exception as e:
                if attempt == max_retries - 1:
                    logging.error(f"Batch {batch_idx} failed permanently: {e}")
                    return batch_idx, [{"results": [], "matched_rank": None} for _ in batch_plans]

                await asyncio.sleep(2)


# -------------------------------------------------------
# Main Runner Entry Point
# -------------------------------------------------------
async def main():
    start_time = time.time()

    logging.info(f"Reading search dataset from {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    
    target_ids = df["materialId"].tolist() if "materialId" in df.columns else [None] * len(df)
    queries = df["query_text"].fillna("").tolist()

    plans = [build_query_plan(q) for q in queries]
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async with httpx.AsyncClient(timeout=None) as client:
        tasks = [
            process_batch_merged(
                sem,
                client,
                idx,
                plans[i : i + BATCH_SIZE],
                target_ids[i : i + BATCH_SIZE]
            )
            for idx, i in enumerate(range(0, len(plans), BATCH_SIZE))
        ]
        results = await asyncio.gather(*tasks)

    # Re-sort to preserve original order
    results.sort(key=lambda x: x[0])
    all_final_outputs = [out for _, batch in results for out in batch]

    # Map directly onto original dataframe shape
    output_df = pd.DataFrame()
    output_df["materialId"] = df["materialId"]
    output_df["query_text"] = df["query_text"]
    output_df["matched_rank"] = [out["matched_rank"] for out in all_final_outputs]

    # Extract up to TOP_K output details
    for rank in range(TOP_K):
        output_df[f"materialId_{rank + 1}"] = [
            out["results"][rank]["materialId"] if len(out["results"]) > rank else None
            for out in all_final_outputs
        ]
        output_df[f"brand_{rank + 1}"] = [
            out["results"][rank]["brandName"] if len(out["results"]) > rank else None
            for out in all_final_outputs
        ]
        output_df[f"product_{rank + 1}"] = [
            out["results"][rank]["productName"] if len(out["results"]) > rank else None
            for out in all_final_outputs
        ]
        output_df[f"score_{rank + 1}"] = [
            out["results"][rank]["score"] if len(out["results"]) > rank else None
            for out in all_final_outputs
        ]

    output_df.to_csv(OUTPUT_FILE, index=False)

    total_time = round(time.time() - start_time, 2)
    logging.info(f"Finished evaluation in {total_time} seconds.")
    logging.info(f"Saved collated evaluation results to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())