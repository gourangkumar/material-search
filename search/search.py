
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import typesense

from config import config
from text_utils import clean_general_text, extract_model_numbers, dehyphenate_model_numbers

logger = logging.getLogger("material-search")

PRIMARY_COLLECTION = "materials_master"
TEMP_COLLECTION = "materials_temp"

# Pool size per tier per collection before global ranking.
TIER_POOL_SIZE = 15


MASTER_SOURCE_FACTOR = 1.02
TEMP_SOURCE_FACTOR = 1.00
BRAND_MATCH_FACTOR = 1.12
GENERIC_MISMATCH_FACTOR = 0.92

GENERIC_BRANDS = {
    "generic",
    "generic brand",
    "unknown",
    "unbranded",
    "na",
    "n/a",
    "-",
}


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
    ("tecno", "techno"),
]

PIPELINE_CONFIG = {
    "QUERY_BY": "modelNumbers,brandName,productName,productSpecification,generalText",
    "QUERY_BY_WEIGHTS": "3,1,1,2,6",
    "NUM_TYPOS": "1,1,2,2,2",
}


def _typesense_client() -> typesense.Client:
    return typesense.Client({
        "nodes": [{
            "host": config.TYPESENSE_HOST,
            "port": str(config.TYPESENSE_PORT),
            "protocol": config.TYPESENSE_PROTOCOL,
        }],
        "api_key": config.TYPESENSE_API_KEY,
        "connection_timeout_seconds": 5,
    })


# ---------------------------------------------------------------------
# Query variant generation
# ---------------------------------------------------------------------
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


def _expand_query_variants(cleaned_query: str, max_variants: int = 4) -> List[str]:
    variants = [cleaned_query]
    generators = [_dimension_variants, _dimension_chain_variants, _unit_spacing_variants, _synonym_variants]
    for fn in generators:
        for v in fn(cleaned_query):
            if v not in variants:
                variants.append(v)
        if len(variants) >= max_variants:
            break
    return variants[:max_variants]


def _extract_number_units(text: str) -> List[Tuple[str, str]]:
    return [(m.group(1), m.group(2).lower()) for m in _NUM_UNIT_RE.finditer(text)]


def _build_query_plan(raw_text: str) -> Dict[str, Any]:
    cleaned = clean_general_text(raw_text)
    model_numbers = extract_model_numbers(raw_text)
    full_query = f"{cleaned} {model_numbers}".strip() if model_numbers else cleaned

    variants = _expand_query_variants(full_query)
    variants = [v for v in variants if v.strip()]
    if not variants:
        fallback = raw_text.strip()
        variants = [fallback] if fallback else ["*"]

    return {
        "cleaned_query": cleaned,
        "model_numbers": model_numbers,
        "model_numbers_dehyphenated": dehyphenate_model_numbers(model_numbers),
        "variants": variants,
    }



def _text_search_request(q: str, per_page: int, collection: str) -> Dict[str, Any]:
    return {
        "collection": collection,
        "q": q,
        "query_by": PIPELINE_CONFIG["QUERY_BY"],
        "query_by_weights": PIPELINE_CONFIG["QUERY_BY_WEIGHTS"],
        "num_typos": PIPELINE_CONFIG["NUM_TYPOS"],
        "per_page": per_page,
        "prefix": True,
        "drop_tokens_threshold": 1,
        "typo_tokens_threshold": 2,
        "prioritize_num_matching_fields": True,
        "text_match_type": "sum_score",
        "include_fields": "materialId,brandName,productName,productSpecification,categoryName",
    }


def _exact_model_request(model_numbers: str, per_page: int, collection: str) -> Dict[str, Any]:
    return {
        "collection": collection,
        "q": model_numbers,
        "query_by": "modelNumbers",
        "num_typos": "0",
        "prefix": False,
        "infix": "fallback",
        "per_page": per_page,
        "include_fields": "materialId,brandName,productName,productSpecification,categoryName",
    }


def _number_unit_request(cleaned_query: str, per_page: int, collection: str) -> Optional[Dict[str, Any]]:
    pairs = _extract_number_units(cleaned_query)
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
        "include_fields": "materialId,brandName,productName,productSpecification,categoryName",
    }


def _normalize_text(value: Any) -> str:
    """Normalize text for conservative brand matching only."""
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_generic_brand(brand: Any) -> bool:
    normalized = _normalize_text(brand)
    return not normalized or normalized in GENERIC_BRANDS


def _brand_occurs_in_query(brand: Any, query: str) -> bool:
    """Return True only when the full known brand appears in the query.

    We deliberately do NOT infer a brand from the first word of the query.
    The brand must come from a real indexed brandName returned by the search
    candidates, which keeps this logic conservative.
    """
    brand_norm = _normalize_text(brand)
    query_norm = _normalize_text(query)

    if not brand_norm or _is_generic_brand(brand_norm):
        return False
    if len(brand_norm) < 2:
        return False

    # Word-boundary matching after normalization. This also handles brands
    # containing spaces, e.g. "Asian Paints".
    return re.search(rf"(?<!\w){re.escape(brand_norm)}(?!\w)", query_norm) is not None


def _hit_to_doc(hit: Dict[str, Any], source: str, kind: str, query_variant: Optional[str] = None) -> Dict[str, Any]:
    doc = hit["document"]
    return {
        "materialId": doc.get("materialId"),
        "brandName": doc.get("brandName"),
        "productName": doc.get("productName"),
        "productSpecification": doc.get("productSpecification"),
        "categoryName": doc.get("categoryName"),
        "score": hit.get("text_match") or 0,
        "source": source,
        "match_type": kind,
        "query_variant": query_variant,
        # Filled during global ranking once candidate brands are known.
        "brand_match": False,
        "ranking_score": 0.0,
    }


class SearchService:
    
    def __init__(self):
        self._client = _typesense_client()

    def _build_searches_for_collection(
        self,
        plan: Dict[str, Any],
        collection: str,
        pool: int,
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[str, Optional[str]]]]:
        searches: List[Dict[str, Any]] = []
        metadata: List[Tuple[str, Optional[str]]] = []

        # 1. Exact-model tier.
        if plan["model_numbers"]:
            searches.append(_exact_model_request(plan["model_numbers"], pool, collection))
            metadata.append(("exact_model", None))

            dehy = plan["model_numbers_dehyphenated"]
            if dehy and dehy != plan["model_numbers"]:
                searches.append(_exact_model_request(dehy, pool, collection))
                metadata.append(("exact_model", None))

        # 2. Number-unit tier.
        nu_req = _number_unit_request(plan["cleaned_query"], pool, collection)
        if nu_req is not None:
            searches.append(nu_req)
            metadata.append(("number_unit", None))

        # 3. Variant-expansion tier.
        for variant in plan["variants"]:
            searches.append(_text_search_request(variant, pool, collection))
            metadata.append(("variant", variant))

        return searches, metadata

    def _extract_query_brands(self, docs: List[Dict[str, Any]], query: str) -> set:
        """Find explicit brands mentioned in the query from returned candidates."""
        query_brands = set()
        for doc in docs:
            brand = doc.get("brandName")
            normalized = _normalize_text(brand)
            if normalized and not _is_generic_brand(normalized) and _brand_occurs_in_query(normalized, query):
                query_brands.add(normalized)
        return query_brands

    def _rank_candidates(self, candidates: List[Tuple[int, float, Dict[str, Any]]], query: str) -> List[Dict[str, Any]]:
        """Apply source + explicit-brand ranking without replacing tier logic."""
        docs = [doc for _, _, doc in candidates]
        query_brands = self._extract_query_brands(docs, query)
        has_explicit_brand = bool(query_brands)

        ranked: List[Tuple[int, float, Dict[str, Any]]] = []

        for priority, raw_score, doc in candidates:
            brand_norm = _normalize_text(doc.get("brandName"))
            brand_match = bool(brand_norm and brand_norm in query_brands)
            generic = _is_generic_brand(brand_norm)

            source_factor = (
                MASTER_SOURCE_FACTOR
                if doc.get("source") == PRIMARY_COLLECTION
                else TEMP_SOURCE_FACTOR
            )

            adjusted_score = float(raw_score or 0) * source_factor

            if has_explicit_brand:
                if brand_match:
                    adjusted_score *= BRAND_MATCH_FACTOR
                elif generic:
                    adjusted_score *= GENERIC_MISMATCH_FACTOR

            doc["brand_match"] = brand_match
            doc["ranking_score"] = adjusted_score
            doc["explicit_brand_query"] = has_explicit_brand


            ranked.append((priority, adjusted_score, doc))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [doc for _, _, doc in ranked]

    def suggest(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        plan = _build_query_plan(query)
        pool = TIER_POOL_SIZE


        searches: List[Dict[str, Any]] = []
        metadata: List[Tuple[str, str, Optional[str]]] = []

        for collection in (PRIMARY_COLLECTION, TEMP_COLLECTION):
            collection_searches, collection_metadata = self._build_searches_for_collection(
                plan, collection, pool
            )
            searches.extend(collection_searches)
            metadata.extend((kind, collection, variant) for kind, variant in collection_metadata)

        try:
            response = self._client.multi_search.perform({"searches": searches}, {})
        except Exception as e:
            logger.error(f"Typesense multi_search failed for query '{query}': {e}")
            raise

        results = response.get("results", [])

        candidates: List[Tuple[int, float, Dict[str, Any]]] = []

        # Keep variant material IDs separately PER COLLECTION. This preserves
        # the original corroboration rule without cross-collection deduping.
        variant_mids_by_source: Dict[str, set] = {
            PRIMARY_COLLECTION: set(),
            TEMP_COLLECTION: set(),
        }
        deferred_results: List[Tuple[Dict[str, Any], str]] = []

        for (kind, collection, query_variant), result in zip(metadata, results):
            if kind == "number_unit":
                deferred_results.append((result, collection))
                continue

            priority = 2 if kind == "exact_model" else 0

            for hit in result.get("hits", []):
                doc = _hit_to_doc(hit, collection, kind, query_variant)
                if doc["materialId"] is None:
                    continue

                if kind == "variant":
                    variant_mids_by_source[collection].add(doc["materialId"])

                candidates.append((priority, float(doc["score"]), doc))

        # Number-unit tier is corroborated only by a variant hit from the
        # SAME collection, mirroring the original pipeline's behaviour.
        for result, collection in deferred_results:
            variant_mids = variant_mids_by_source[collection]

            for hit in result.get("hits", []):
                doc = _hit_to_doc(hit, collection, "number_unit", None)
                if doc["materialId"] is None:
                    continue

                corroborated = doc["materialId"] in variant_mids
                priority = 1 if corroborated else 0
                candidates.append((priority, float(doc["score"]), doc))


        best_by_source_and_material: Dict[Tuple[str, Any], Tuple[int, float, Dict[str, Any]]] = {}

        for priority, score, doc in candidates:
            key = (doc["source"], doc["materialId"])
            current = best_by_source_and_material.get(key)
            if current is None or (priority, score) > (current[0], current[1]):
                best_by_source_and_material[key] = (priority, score, doc)

        merged_candidates = list(best_by_source_and_material.values())
        ranked_docs = self._rank_candidates(merged_candidates, query)

        # Return the globally best N candidates from both collections.
        return ranked_docs[:limit]


search_service = SearchService()
