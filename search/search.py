import typesense
from config import config
from text_utils import clean_general_text, extract_model_numbers

# Same field weighting used in evaluate_search.py - keep these two files in
# sync, since search.py is what actually serves live autocomplete traffic
# and evaluate_search.py is how you measure it. If you tune one, tune both.
#
# categoryName is DELIBERATELY EXCLUDED from query_by. Eval evidence showed
# ERP department/category-label prefixes (e.g. "Office Suppliers -",
# "ELECTRONICS and INST", "Mechanical and Power Transmission") achieve a
# near-complete match ratio against the short categoryName field, turning a
# handful of documents into "magnet" results that win regardless of the
# actual item requested. It remains an indexed+facetable field, just not
# part of the searched text.
QUERY_BY = "modelNumbers,brandName,productName,productSpecification,generalText"
QUERY_BY_WEIGHTS = "5,3,2,2,1"
NUM_TYPOS = "1,1,2,2,2"


def build_query_string(raw_query: str) -> str:
    """Same cleaning pipeline used at index time and in evaluate_search.py,
    so live queries and offline eval queries are treated identically."""
    general = clean_general_text(raw_query)
    models = extract_model_numbers(raw_query)
    if models:
        return f"{general} {models}".strip()
    return general


class SearchService:
    def __init__(self):
        self.client = typesense.Client({
            'nodes': [{
                'host': config.TYPESENSE_HOST,
                'port': str(config.TYPESENSE_PORT),
                'protocol': config.TYPESENSE_PROTOCOL
            }],
            'api_key': config.TYPESENSE_API_KEY,
            'connection_timeout_seconds': 5
        })

    def _build_search_params(self, query: str, per_page: int):
        return {
            'q': query,
            'query_by': QUERY_BY,
            'query_by_weights': QUERY_BY_WEIGHTS,
            'num_typos': NUM_TYPOS,
            'text_match_type': 'sum_score',
            'sort_by': '_text_match:desc,mat_qty:desc',
            'per_page': per_page,
            'prefix': True,
            'drop_tokens_threshold': 1,
            'typo_tokens_threshold': 1,
        }

    def suggest(self, query: str, limit: int = 5):
        cleaned_query = build_query_string(query)

        # If cleaning stripped everything (e.g. query was pure stop-words/
        # punctuation), fall back to the raw string rather than sending an
        # empty q to Typesense.
        if not cleaned_query:
            cleaned_query = query.strip()

        # Step 1: Search Primary Master Collection
        primary_search = self._build_search_params(cleaned_query, limit)
        primary_res = self.client.collections['materials_master'].documents.search(primary_search)
        results = [hit['document'] for hit in primary_res.get('hits', [])]

        # Step 2: Fallback to Temp Collection if primary doesn't meet the required limit
        remaining_slots = limit - len(results)
        if remaining_slots > 0:
            temp_search = self._build_search_params(cleaned_query, remaining_slots)
            temp_res = self.client.collections['materials_temp'].documents.search(temp_search)
            temp_hits = [hit['document'] for hit in temp_res.get('hits', [])]
            results.extend(temp_hits)

        return results


search_service = SearchService()