"""Location extract + match helpers for hunt sourcing filters."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

# Strong non-India country / region signals (reject for India hunts)
_NON_INDIA_RE = re.compile(
    r"\b("
    r"united\s+states|usa|u\.s\.a\.|u\.s\.|"
    r"georgia|atlanta|california|new\s+york|texas|florida|illinois|seattle|chicago|"
    r"san\s+francisco|los\s+angeles|boston|austin|denver|miami|"
    r"italy|italia|milan|milano|rome|roma|monza|lombardy|lombardia|turin|torino|"
    r"united\s+kingdom|england|scotland|london|manchester|"
    r"germany|deutschland|berlin|munich|frankfurt|"
    r"france|paris|lyon|"
    r"spain|madrid|barcelona|"
    r"netherlands|amsterdam|"
    r"canada|toronto|vancouver|"
    r"australia|sydney|melbourne|"
    r"singapore|dubai|uae|saudi|"
    r"brazil|mexico|japan|china|korea|poland|sweden|switzerland"
    r")\b",
    re.I,
)

# India positive signals
_INDIA_RE = re.compile(
    r"\b("
    r"india|bharat|"
    r"bengaluru|bangalore|mumbai|delhi|new\s+delhi|hyderabad|chennai|pune|kolkata|"
    r"gurgaon|gurugram|noida|ghaziabad|faridabad|"
    r"ahmedabad|jaipur|chandigarh|kochi|coimbatore|indore|lucknow|bhopal|"
    r"thiruvananthapuram|trivandrum|mysore|mysuru|nagpur|surat|vadodara|"
    r"andhra|telangana|karnataka|maharashtra|tamil\s+nadu|kerala|gujarat|"
    r"rajasthan|west\s+bengal|uttar\s+pradesh|haryana|punjab"
    r")\b",
    re.I,
)

# LinkedIn geo host → country label
_LI_HOST_COUNTRY = {
    "in": "India",
    "it": "Italy",
    "uk": "United Kingdom",
    "de": "Germany",
    "fr": "France",
    "es": "Spain",
    "nl": "Netherlands",
    "ca": "Canada",
    "au": "Australia",
    "br": "Brazil",
    "mx": "Mexico",
    "jp": "Japan",
    "sg": "Singapore",
    "ae": "United Arab Emirates",
    "pl": "Poland",
    "se": "Sweden",
    "ch": "Switzerland",
}


def linkedin_host_country(url: str) -> Optional[str]:
    """Map ``it.linkedin.com`` / ``in.linkedin.com`` → country name."""
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = url.lower()
    m = re.match(r"^([a-z]{2})\.linkedin\.com$", host)
    if m:
        return _LI_HOST_COUNTRY.get(m.group(1))
    if host in {"www.linkedin.com", "linkedin.com"}:
        return None  # global — unknown
    return None


def extract_location_from_text(*parts: str) -> Optional[str]:
    """Best-effort location line from LinkedIn/Naukri profile text."""
    blob = "\n".join(p for p in parts if p)
    if not blob:
        return None

    # Common LinkedIn patterns
    patterns = [
        r"(?:location|based in|lives in|area)[:\s]+([^\n|]{3,80})",
        r"\b([A-Z][a-zA-Z .'-]+,\s*[A-Z][a-zA-Z .'-]+(?:,\s*[A-Z][a-zA-Z .'-]+)?)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, blob, re.I):
            cand = m.group(1).strip(" ·|-")
            if 3 <= len(cand) <= 80 and not re.search(r"https?://", cand, re.I):
                # A comma alone is not geographic evidence (company names often contain one).
                if _INDIA_RE.search(cand) or _NON_INDIA_RE.search(cand):
                    return cand[:100]

    # Scan early lines for city, region patterns
    for line in blob.splitlines()[:40]:
        line = line.strip()
        if len(line) < 4 or len(line) > 90:
            continue
        low = line.lower()
        if any(x in low for x in ("linkedin", "cookie", "follow", "message", "connect", "http")):
            continue
        if _INDIA_RE.search(line) or _NON_INDIA_RE.search(line):
            return line[:100]
    return None


def location_matches_target(
    *,
    candidate_location: Optional[str],
    target_location: Optional[str],
    profile_url: str = "",
    page_text: str = "",
    reject_unknown: bool = True,
) -> Tuple[bool, str]:
    """Return (ok, reason). Hard-filter when hunt targets India (or other geo)."""
    target = (target_location or "").strip()
    if not target:
        return True, "no_target"

    target_l = target.lower()
    wants_india = bool(re.search(r"\bindia\b", target_l)) or target_l in {"in", "ind"}

    blob = " ".join(
        x for x in [candidate_location or "", page_text or "", profile_url or ""] if x
    )
    host_country = linkedin_host_country(profile_url)

    if wants_india:
        # Explicit foreign LinkedIn TLD
        if host_country and host_country != "India":
            return False, f"linkedin_host:{host_country}"

        non = _NON_INDIA_RE.search(blob)
        ind = _INDIA_RE.search(blob)

        # Clear foreign signal without India → reject
        if non and not ind:
            return False, f"non_india:{non.group(0)}"

        # India evidence → pass
        if ind or host_country == "India":
            return True, "india_match"

        if reject_unknown:
            return False, "unknown_location_for_india_hunt"
        return True, "unknown_allowed"

    # Generic: require target token somewhere, or fail closed if unknown
    if target_l in (candidate_location or "").lower() or target_l in (page_text or "").lower():
        return True, "token_match"
    if host_country and host_country.lower() == target_l:
        return True, "host_match"
    if reject_unknown:
        # Soft: if no contradictory info and target is vague (e.g. Remote), allow
        if target_l in {"remote", "anywhere", "worldwide", "global"}:
            return True, "remote_ok"
        return False, "location_mismatch"
    return True, "unknown_allowed"


def normalize_candidate_location(
    *,
    extracted: Optional[str],
    profile_url: str = "",
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Prefer extracted profile location; never invent hunt country as candidate home."""
    if extracted and extracted.strip():
        return extracted.strip()[:100]
    host = linkedin_host_country(profile_url)
    if host:
        return host
    # Do NOT use hunt fallback as the person's location — leave unknown
    return None
