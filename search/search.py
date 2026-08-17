import re
from typing import Any, Dict, List, Optional, Tuple

import typesense

from config import config
from text_utils import clean_general_text, extract_model_numbers

try:
    from text_utils import dehyphenate_model_numbers
except ImportError:
    def dehyphenate_model_numbers(model_numbers: str) -> str:
        if not model_numbers:
            return ""
        seen = set()
        out = []
        for token in model_numbers.split():
            token = token.replace("-", "").replace("/", "")
            if token and token not in seen:
                out.append(token)
                seen.add(token)
        return " ".join(out)



QUERY_BY = "modelNumbers,brandName,productName,productSpecification,generalText"
QUERY_BY_WEIGHTS = "3,1,1,2,6"
NUM_TYPOS = "1,1,2,2,2"

# Keep exact identifier searches strict.
EXACT_NUM_TYPOS = "0"

# Avoid exploding autocomplete latency.
MAX_VARIANT_SEARCHES = 4

# For short autocomplete fragments, prefix matching is useful.
# For complete queries, evaluator-style full-token matching is safer.
PREFIX_QUERY_MAX_CHARS = 3

# Common engineering units. Kept deliberately conservative.
UNIT_PATTERN = (
    r"(?:mm|cm|m|km|kg|g|mg|ml|l|kw|w|hp|rpm|psi|bar|"
    r"awg|swg|v|a|amp|amps|sqmm|sqcm|inch|in|ft|nb|id|od)"
)

SYMMETRIC_SYNONYMS = (
    ("screw driver", "screwdriver"),
    ("core", "cores"),
    ("cable", "cables"),
    ("v belt", "v-belt"),
    ("tecno", "techno"),
)



def _dimension_variants(text: str) -> List[str]:
    out: List[str] = []

    normalized = re.sub(
        r"(?<=\d)\s*[*×Xx]\s*(?=\d)",
        "x",
        text,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "x", normalized)

    spaced = re.sub(r"(?<=\d)x(?=\d)", " x ", normalized)
    fused = re.sub(r"(?<=\d)\s+x\s+(?=\d)", "x", normalized)

    for value in (normalized, spaced, fused):
        value = re.sub(r"\s+", " ", value).strip()
        if value and value != text and value not in out:
            out.append(value)

    return out


def _dimension_chain_variants(text: str) -> List[str]:
    """
    Specifically handle dimension chains such as:
        10-20-30
        10 x 20 x 30
    """
    out: List[str] = []

    chain_pattern = r"\b(\d+(?:\.\d+)?)(?:\s*[-x×X*]\s*)(\d+(?:\.\d+)?)(?:\s*[-x×X*]\s*)(\d+(?:\.\d+)?)\b"

    for match in re.finditer(chain_pattern, text, flags=re.IGNORECASE):
        a, b, c = match.groups()
        candidates = [
            f"{a}x{b}x{c}",
            f"{a} x {b} x {c}",
        ]
        for candidate in candidates:
            if candidate not in out:
                out.append(candidate)

    return out


def _unit_spacing_variants(text: str) -> List[str]:
    """
    Handle:
        20mm <-> 20 mm
        5kg  <-> 5 kg
    """
    out: List[str] = []

    spaced = re.sub(
        rf"(\d+(?:\.\d+)?)({UNIT_PATTERN})\b",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )
    fused = re.sub(
        rf"(\d+(?:\.\d+)?)\s+({UNIT_PATTERN})\b",
        r"\1\2",
        text,
        flags=re.IGNORECASE,
    )

    for value in (spaced, fused):
        value = re.sub(r"\s+", " ", value).strip()
        if value != text and value not in out:
            out.append(value)

    return out


def _synonym_variants(text: str) -> List[str]:
    out: List[str] = []

    for a, b in SYMMETRIC_SYNONYMS:
        if a in text:
            value = text.replace(a, b)
            if value not in out:
                out.append(value)

        if b in text:
            value = text.replace(b, a)
            if value not in out:
                out.append(value)

    return out


def expand_query_variants(
    cleaned_query: str,
    max_variants: int = MAX_VARIANT_SEARCHES,
) -> List[str]:
    variants = [cleaned_query]

    generators = (
        _dimension_variants,
        _dimension_chain_variants,
        _unit_spacing_variants,
        _synonym_variants,
    )

    for generator in generators:
        for value in generator(cleaned_query):
            if value and value not in variants:
                variants.append(value)
            if len(variants) >= max_variants:
                return variants[:max_variants]

    return variants[:max_variants]


def _extract_number_unit_pairs(text: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []

    pattern = rf"\b(\d+(?:\.\d+)?)\s*({UNIT_PATTERN})\b"

    for number, unit in re.findall(pattern, text, flags=re.IGNORECASE):
        pair = (number, unit.lower())
        if pair not in pairs:
            pairs.append(pair)

    return pairs


def build_query_plan(raw_query: str) -> Dict[str, Any]:
    cleaned = clean_general_text(raw_query)
    models = extract_model_numbers(raw_query)

    full_query = f"{cleaned} {models}".strip() if models else cleaned

    if not full_query:
        full_query = str(raw_query).strip()

    variants = expand_query_variants(full_query)

    dehyphenated = dehyphenate_model_numbers(models)

    return {
        "cleaned_query": cleaned,
        "full_query": full_query,
        "model_numbers": models,
        "model_numbers_dehyphenated": dehyphenated,
        "variants": variants or [full_query],
        "number_unit_pairs": _extract_number_unit_pairs(cleaned),
    }



def _build_weighted_params(
    query: str,
    per_page: int,
    prefix: bool,
) -> Dict[str, Any]:
    return {
        "q": query,
        "query_by": QUERY_BY,
        "query_by_weights": QUERY_BY_WEIGHTS,
        "num_typos": NUM_TYPOS,
        "text_match_type": "sum_score",
        "per_page": max(1, per_page),
        "prefix": prefix,
        "drop_tokens_threshold": 1,
        "typo_tokens_threshold": 2,
        "prioritize_num_matching_fields": True,
        "include_fields": (
            "materialId,brandName,productName,variantName,categoryName,"
            "productSpecification,generalText,listPrice,UOM,shortDescription,"
            "vendors,ARCvendors,mat_qty"
        ),
    }


def _build_exact_model_params(
    model_query: str,
    per_page: int,
) -> Dict[str, Any]:
    return {
        "q": model_query,
        "query_by": "modelNumbers",
        "num_typos": EXACT_NUM_TYPOS,
        "text_match_type": "sum_score",
        "per_page": max(1, per_page),
        "prefix": False,
        "prioritize_num_matching_fields": True,
        "include_fields": (
            "materialId,brandName,productName,variantName,categoryName,"
            "productSpecification,generalText,listPrice,UOM,shortDescription,"
            "vendors,ARCvendors,mat_qty"
        ),
    }


def _build_number_unit_params(
    phrase: str,
    per_page: int,
) -> Dict[str, Any]:
    return {
        "q": phrase,
        "query_by": "productSpecification",
        "num_typos": EXACT_NUM_TYPOS,
        "text_match_type": "sum_score",
        "per_page": max(1, per_page),
        "prefix": False,
        "drop_tokens_threshold": 0,
        "prioritize_num_matching_fields": True,
        "include_fields": (
            "materialId,brandName,productName,variantName,categoryName,"
            "productSpecification,generalText,listPrice,UOM,shortDescription,"
            "vendors,ARCvendors,mat_qty"
        ),
    }



def _material_id(document: Dict[str, Any]) -> str:
    return str(
        document.get("materialId")
        or document.get("MaterialId")
        or document.get("id")
        or ""
    ).strip()


def _safe_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _merge_documents(
    existing: Dict[str, Dict[str, Any]],
    hits: List[Dict[str, Any]],
    tier: int,
) -> None:
    """
    Merge by materialId.

    tier:
        0 = exact model
        1 = exact number/unit
        2 = normal weighted search

    Lower tier wins when the same material is returned by multiple searches.
    """
    for rank, document in enumerate(hits):
        mid = _material_id(document)
        if not mid:
            mid = f"__anonymous__{id(document)}"

        candidate = {
            "document": document,
            "tier": tier,
            "rank": rank,
        }

        current = existing.get(mid)

        if current is None:
            existing[mid] = candidate
            continue

        if (tier, rank) < (current["tier"], current["rank"]):
            existing[mid] = candidate


def _final_sort_key(item: Dict[str, Any]) -> Tuple[int, int, float]:
    """
    Exact identifier matches first, then exact number/unit matches, then
    normal relevance. Within a tier, preserve Typesense's ranking and use
    mat_qty only as a late tie-breaker.
    """
    document = item["document"]
    tier = item["tier"]
    rank = item["rank"]

    return (
        tier,
        rank,
        -_safe_number(document.get("mat_qty", 0)),
    )



class SearchService:
    def __init__(self):
        self.client = typesense.Client(
            {
                "nodes": [
                    {
                        "host": config.TYPESENSE_HOST,
                        "port": str(config.TYPESENSE_PORT),
                        "protocol": config.TYPESENSE_PROTOCOL,
                    }
                ],
                "api_key": config.TYPESENSE_API_KEY,
                "connection_timeout_seconds": 5,
            }
        )

    def _search_collection(
        self,
        collection_name: str,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        try:
            response = (
                self.client.collections[collection_name]
                .documents.search(params)
            )
            return [
                hit.get("document", {})
                for hit in response.get("hits", [])
                if hit.get("document")
            ]
        except Exception:
            return []

    def _search_both_collections(
        self,
        params: Dict[str, Any],
        per_collection: int,
    ) -> List[Dict[str, Any]]:
        local_params = dict(params)
        local_params["per_page"] = max(1, per_collection)

        primary = self._search_collection(
            "materials_master",
            local_params,
        )
        temporary = self._search_collection(
            "materials_temp",
            local_params,
        )

        merged: List[Dict[str, Any]] = []
        seen = set()

        for document in primary + temporary:
            mid = _material_id(document)
            key = mid or f"__anonymous__{id(document)}"

            if key in seen:
                continue

            seen.add(key)
            merged.append(document)

        return merged

    def suggest(self, query: str, limit: int = 5):
        raw_query = (query or "").strip()

        if not raw_query:
            return []

        plan = build_query_plan(raw_query)

        cleaned_query = plan["full_query"]
        if not cleaned_query:
            cleaned_query = raw_query

        candidates: Dict[str, Dict[str, Any]] = {}

        models = plan["model_numbers"]
        dehyphenated_models = plan["model_numbers_dehyphenated"]

        model_queries: List[str] = []

        if models:
            model_queries.append(models)

        if dehyphenated_models and dehyphenated_models != models:
            model_queries.append(dehyphenated_models)

        for model_query in model_queries[:2]:
            params = _build_exact_model_params(
                model_query,
                max(limit, 5),
            )

            hits = self._search_both_collections(
                params,
                max(limit, 5),
            )

            _merge_documents(candidates, hits, tier=0)

        pairs = plan["number_unit_pairs"]

        if pairs:
            phrase = " ".join(
                f"{number}{unit}"
                for number, unit in pairs
            )

            params = _build_number_unit_params(
                phrase,
                max(limit, 5),
            )

            hits = self._search_both_collections(
                params,
                max(limit, 5),
            )

            _merge_documents(candidates, hits, tier=1)

        prefix = len(raw_query) <= PREFIX_QUERY_MAX_CHARS

        for variant in plan["variants"][:MAX_VARIANT_SEARCHES]:
            if not variant:
                continue

            params = _build_weighted_params(
                variant,
                max(limit, 5),
                prefix=prefix,
            )

            hits = self._search_both_collections(
                params,
                max(limit, 5),
            )

            _merge_documents(candidates, hits, tier=2)

        ranked = sorted(
            candidates.values(),
            key=_final_sort_key,
        )

        results = [
            item["document"]
            for item in ranked[:limit]
        ]

        return results


search_service = SearchService()
