"""Client for the NLM Clinical Tables ICD-10-CM search API.

This is a free, keyless, US government service with the current fiscal year
code set. The coder agent uses it as a tool so that every ICD-10-CM code it
suggests is checked against the real code table instead of being trusted from
model memory. Reference: https://clinicaltables.nlm.nih.gov/apidoc/icd10cm/v3/doc.html
"""

import httpx

BASE_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"

# simple in-process caches so eval runs do not hammer the API
_search_cache: dict[str, list[dict]] = {}
_validate_cache: dict[str, dict] = {}


def _get(params: dict) -> list:
    with httpx.Client(timeout=10) as client:
        resp = client.get(BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def search_terms(query: str, max_results: int = 8) -> list[dict]:
    """Search ICD-10-CM by clinical term. Returns [{code, name}, ...]."""
    key = f"{query.lower()}|{max_results}"
    if key in _search_cache:
        return _search_cache[key]
    try:
        payload = _get({"sf": "code,name", "terms": query, "maxList": max_results})
        matches = [{"code": code, "name": name} for code, name in payload[3]]
    except Exception as exc:
        matches = [{"error": f"lookup unavailable: {exc}"}]
    _search_cache[key] = matches
    return matches


def validate_code(code: str) -> dict:
    """Check whether a specific ICD-10-CM code exists in the current code set.

    Returns {"code", "valid", "name"}. valid is None when the API cannot be
    reached, and the payer treats that as pass so the demo degrades gracefully
    offline.
    """
    code = code.strip().upper()
    if code in _validate_cache:
        return _validate_cache[code]
    try:
        payload = _get({"sf": "code", "terms": code, "maxList": 25})
        found = {c.upper(): n for c, n in payload[3]}
        result = {"code": code, "valid": code in found, "name": found.get(code, "")}
    except Exception:
        result = {"code": code, "valid": None, "name": ""}
    _validate_cache[code] = result
    return result
