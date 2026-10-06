"""Wikimedia Commons client used to attach photos to catalogue destinations.

Design notes
------------
* **No new dependencies.**  The project ships Flask + pytest only, so the HTTP
  layer is ``urllib.request`` from the standard library.
* **Polite by default.**  Wikimedia's User-Agent policy requires a descriptive
  agent string; a generic ``Python-urllib`` agent gets throttled or blocked.
  Every call therefore sends ``USER_AGENT`` and pauses ``min_interval``
  seconds between requests.
* **Failures are values, not crashes.**  The caller receives an
  :class:`ImageSearchResult` whose ``error`` explains what went wrong
  (network, HTTP 429/5xx, malformed JSON) instead of an exception, so one bad
  destination can never abort a 525-row batch.
* **HTML is stripped.**  ``extmetadata.Artist`` is HTML
  (``<a href=...>Name</a>``); storing it raw would inject markup into the
  page, so :func:`strip_html` reduces it to plain text.
"""

from __future__ import annotations

import html
import json
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

#: Wikimedia asks every client to identify itself with a contact URL.
USER_AGENT = ("Wize-Destination-Images/1.0 "
              "(https://github.com/wize/wize; educational project) "
              "python-urllib/3")

#: File types we are willing to embed.  Commons also hosts SVG/PDF/TIF which
#: either do not render in an <img> tag or are huge, so they are filtered out.
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png")

#: Licences that are freely reusable.  Anything else (fair use, "permission
#: granted", all-rights-reserved) is rejected so the catalogue stays legally
#: clean.  Compared case-insensitively against the licence short name.
ALLOWED_LICENCE_KEYWORDS = ("cc", "public domain", "pd-", "no restrictions",
                            "attribution", "gfdl")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: Commons file names are prefixed "File:"; the rest is the meaningful stem.
_FILE_PREFIX_RE = re.compile(r"^file\s*:\s*", re.IGNORECASE)


class CommonsError(Exception):
    """Raised internally when a request cannot be completed."""


def strip_html(value: str | None) -> str:
    """Reduce a Commons HTML fragment (``Artist``) to plain text.

    Entities are unescaped first so the output reads naturally in the
    attribution line, and whitespace is collapsed.
    """
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _tokenise(text: str | None) -> set[str]:
    """Lower-case, accent-free word set used for matching.

    Mirrors ``models.destination.normalise_name`` so "Kinkaku-ji" and
    "Kinkaku Ji" tokenise identically.
    """
    if not text:
        return set()
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped.lower())
    return {token for token in cleaned.split() if len(token) > 1}


@dataclass(frozen=True)
class ImageCandidate:
    """One plausible Commons file for a destination."""

    title: str
    url: str                      # thumbnail URL embedded on the site
    source_page_url: str          # Commons description page (human readable)
    creator: str
    license_name: str
    license_url: str
    width: int
    height: int
    score: float = 0.0

    @property
    def display_title(self) -> str:
        return _FILE_PREFIX_RE.sub("", self.title)


@dataclass
class ImageSearchResult:
    """Outcome of one destination search - never raises at the call site."""

    candidates: list[ImageCandidate] = field(default_factory=list)
    query: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def best(self) -> ImageCandidate | None:
        return self.candidates[0] if self.candidates else None
def build_query(name: str, city: str | None, country: str | None) -> str:
    """Compose the Commons search string for a destination.

    Name + city + country narrows the search to the right place and is the
    main defence against matching a same-named attraction elsewhere.  Any
    parenthetical disambiguation already in the name is kept, because it is
    usually the strongest matching signal ("Kinkaku-ji (Golden Pavilion)").
    """
    parts = [str(name or "").strip()]
    if city:
        parts.append(str(city).strip())
    if country:
        parts.append(str(country).strip())
    return " ".join(part for part in parts if part).strip()


def score_candidate(name: str, city: str | None, country: str | None,
                    file_title: str) -> float:
    """Confidence (0..1) that ``file_title`` depicts this destination.

    A title is judged on the attraction name tokens plus the location tokens:

    * full name-token overlap             -> +0.6
    * partial name overlap                -> scaled share of that 0.6
    * city present                        -> +0.2
    * country present                     -> +0.1
    * no name token overlap at all        -> hard 0.0 (clearly unrelated)

    The location bonus is what stops "Angkor Wat" in Cambodia from being
    satisfied by an unrelated "Wat" temple in another country.
    """
    name_tokens = _tokenise(name)
    title_tokens = _tokenise(file_title)
    if not name_tokens or not title_tokens:
        return 0.0

    overlap = name_tokens & title_tokens
    if not overlap:
        return 0.0                      # unrelated - never auto-assign

    score = 0.6 * (len(overlap) / len(name_tokens))
    if city and _tokenise(city) & title_tokens:
        score += 0.2
    if country and _tokenise(country) & title_tokens:
        score += 0.1
    return round(min(score, 1.0), 4)


def _is_allowed_licence(licence: str) -> bool:
    """True when the licence short name looks freely reusable."""
    lowered = (licence or "").strip().lower()
    return any(keyword in lowered for keyword in ALLOWED_LICENCE_KEYWORDS)


def build_attribution(candidate: ImageCandidate) -> str:
    """One-line attribution in the form Commons asks for.

    Example: ``"Kinkaku-ji by Basile Morin, CC BY-SA 4.0, via Wikimedia
    Commons"``.
    """
    creator = candidate.creator or "Unknown author"
    licence = candidate.license_name or "see source page"
    return (f"{candidate.display_title} by {creator}, {licence}, "
            f"via Wikimedia Commons")
class CommonsClient:
    """Small, polite wrapper around the Commons ``generator=search`` API."""

    def __init__(self, timeout: float = 10.0, min_interval: float = 0.34,
                 retries: int = 3, backoff: float = 2.0,
                 opener: Callable[[urllib.request.Request, float], Any] | None = None,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.timeout = timeout
        #: ~3 requests/second is well inside Wikimedia's limits for scripts.
        self.min_interval = min_interval
        self.retries = max(1, retries)
        self.backoff = backoff
        #: Injected by the tests so no real network call is ever made.
        self._opener = opener or self._default_opener
        self._sleep = sleeper
        self._last_call = 0.0

    # --------------------------------------------------------------- HTTP --
    @staticmethod
    def _default_opener(request: urllib.request.Request, timeout: float) -> str:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")

    def _throttle(self) -> None:
        """Sleep just enough to honour ``min_interval`` between calls."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            self._sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    def _get_json(self, params: dict[str, str]) -> dict[str, Any]:
        """GET the API with retries; raises :class:`CommonsError` on failure."""
        url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
        last_error = "unknown error"

        for attempt in range(self.retries):
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                self._throttle()
                payload = self._opener(request, self.timeout)
                return json.loads(payload)
            except urllib.error.HTTPError as error:
                last_error = f"HTTP {error.code}"
                # 429 and 5xx are transient - back off and try again.
                if error.code not in (429, 500, 502, 503, 504):
                    raise CommonsError(f"Commons API returned HTTP {error.code}")
            except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
                last_error = f"network error: {error}"
            except json.JSONDecodeError:
                last_error = "malformed JSON from Commons"
            if attempt < self.retries - 1:
                self._sleep(self.backoff ** attempt)

        raise CommonsError(f"Commons API request failed after {self.retries} "
                           f"attempts ({last_error})")
# ------------------------------------------------------------- search --
    def search(self, name: str, city: str | None = None,
               country: str | None = None, limit: int = 10) -> ImageSearchResult:
        """Search Commons for photos of a destination.

        Returns ranked :class:`ImageCandidate` objects (best first).  Network
        and API problems are reported through ``result.error`` rather than
        raised, so a batch run can continue to the next destination.
        """
        query = build_query(name, city, country)
        if not query:
            return ImageSearchResult(query=query, error="empty search query")

        try:
            data = self._get_json({
                "action": "query",
                "format": "json",
                "formatversion": "1",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": "6",          # File: namespace only
                "gsrlimit": str(max(1, min(limit, 50))),
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size",
                "iiurlwidth": "1024",          # request a sane thumbnail
            })
        except CommonsError as error:
            return ImageSearchResult(query=query, error=str(error))

        return ImageSearchResult(query=query,
                                 candidates=self._rank(name, city, country, data))

    def _rank(self, name: str, city: str | None, country: str | None,
              data: dict[str, Any]) -> list[ImageCandidate]:
        """Turn the raw API payload into scored candidates, best first."""
        pages = ((data.get("query") or {}).get("pages") or {})
        if isinstance(pages, list):          # defensive: formatversion drift
            pages = {str(p.get("pageid")): p for p in pages}

        candidates: list[ImageCandidate] = []
        for page in pages.values():
            info_list = page.get("imageinfo") or []
            if not info_list:
                continue
            info = info_list[0]
            title = str(page.get("title") or "")
            if not title.lower().endswith(ALLOWED_EXTENSIONS):
                continue

            metadata = info.get("extmetadata") or {}

            def field_value(key: str, source: dict = metadata) -> str:
                entry = source.get(key)
                return (strip_html(entry.get("value"))
                        if isinstance(entry, dict) else "")

            licence = field_value("LicenseShortName") or field_value("License")
            if not _is_allowed_licence(licence):
                # Non-free or unclear terms - skip rather than mis-attribute.
                continue

            url = info.get("thumburl") or info.get("url")
            source_page = info.get("descriptionurl")
            if not url or not source_page:
                continue

            candidates.append(ImageCandidate(
                title=title,
                url=str(url),
                source_page_url=str(source_page),
                creator=field_value("Artist") or "Unknown author",
                license_name=licence,
                license_url=field_value("LicenseUrl"),
                width=int(info.get("thumbwidth") or info.get("width") or 0),
                height=int(info.get("thumbheight") or info.get("height") or 0),
                score=score_candidate(name, city, country, title),
            ))

        # Highest score first; ties broken by the larger image.
        candidates.sort(key=lambda c: (c.score, c.width * c.height), reverse=True)
        return [c for c in candidates if c.score > 0]