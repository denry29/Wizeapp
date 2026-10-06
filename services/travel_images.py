"""Find and cache relevant, freely licensed images for travel results."""

from __future__ import annotations

import logging
import re
import threading
import time
from functools import lru_cache

from services.commons import CommonsClient, build_attribution

logger = logging.getLogger(__name__)
_commons = CommonsClient(timeout=4, min_interval=0.34, retries=1)
_commons_lock = threading.Lock()
_commons_unavailable_until = 0.0


@lru_cache(maxsize=512)
def commons_image(name: str, city: str, country: str,
                  require_logo: bool = False) -> dict[str, str] | None:
    """Find a closely matched, freely licensed image and keep its attribution."""
    global _commons_unavailable_until
    with _commons_lock:
        now = time.monotonic()
        if now < _commons_unavailable_until:
            return None
        result = _commons.search(name, city or None, country or None, limit=10)
        if result.error:
            logger.warning("Wikimedia Commons image lookup failed: %s", result.error)
            _commons_unavailable_until = now + 30
            return None

    candidates = result.candidates
    if require_logo:
        candidates = [
            candidate for candidate in candidates
            if (
                "logo" in re.findall(r"[a-z]+", candidate.display_title.lower())
                and any(
                    term in re.findall(r"[a-z]+", candidate.display_title.lower())
                    for term in ("airline", "airlines", "airways")
                )
            )
            and candidate.score >= 0.6
        ]
    else:
        candidates = [candidate for candidate in candidates if candidate.score >= 0.8]
    if not candidates:
        return None

    candidate = candidates[0]
    return {
        "url": candidate.url,
        "attribution": build_attribution(candidate),
        "source_url": candidate.source_page_url,
        "license": candidate.license_name,
    }
