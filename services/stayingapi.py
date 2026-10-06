"""Server-side client for StayingAPI hotel search and review data."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

STAYING_API_BASE_URL = "https://api.stayingapi.com/v1"

ASIAN_COUNTRIES = {
    "AE": "United Arab Emirates", "AF": "Afghanistan", "AM": "Armenia",
    "AZ": "Azerbaijan", "BD": "Bangladesh", "BH": "Bahrain",
    "BN": "Brunei", "BT": "Bhutan", "CN": "China", "CY": "Cyprus",
    "GE": "Georgia", "HK": "Hong Kong", "ID": "Indonesia", "IL": "Israel",
    "IN": "India", "IQ": "Iraq", "IR": "Iran", "JO": "Jordan",
    "JP": "Japan", "KG": "Kyrgyzstan", "KH": "Cambodia",
    "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait",
    "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon",
    "LK": "Sri Lanka", "MM": "Myanmar", "MN": "Mongolia",
    "MO": "Macau", "MV": "Maldives", "MY": "Malaysia", "NP": "Nepal",
    "OM": "Oman", "PH": "Philippines", "PK": "Pakistan",
    "PS": "Palestine", "QA": "Qatar", "SA": "Saudi Arabia",
    "SG": "Singapore", "SY": "Syria", "TH": "Thailand",
    "TJ": "Tajikistan", "TL": "Timor-Leste", "TM": "Turkmenistan",
    "TW": "Taiwan", "UZ": "Uzbekistan", "VN": "Vietnam", "YE": "Yemen",
}


class StayingAPIError(Exception):
    """A safe, user-facing StayingAPI failure."""


class StayingAPIClient:
    """Searches real accommodation data without exposing the API key."""

    def __init__(self, api_key: str, *, timeout: float = 20,
                 max_job_wait: float = 600) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise StayingAPIError(
                "Hotel search is unavailable. Configure STAYING_API_KEY on "
                "the Flask server.")
        self.api_key = api_key
        # StayingAPI expects an HTTP Bearer token header; tolerate keys that
        # were pasted into .env with the scheme already included.
        self._auth_header = (api_key if api_key.lower().startswith("bearer ")
                             else f"Bearer {api_key}")
        self.timeout = timeout
        self.max_job_wait = max_job_wait

    def search_hotels(self, city: str, country_code: str, check_in: str,
                      check_out: str, adults: int = 2, rooms: int = 1,
                      children: int = 0, child_ages: list[int] | None = None,
                      currency: str = "USD") -> dict[str, Any]:
        """Search real hotel-platform offers for a specific Asian destination."""
        params: list[tuple[str, str | int]] = [
            ("location", f"{city}, {country_code}"),
            ("platforms", "booking,google"),
            ("propertyType[]", "hotel"),
            ("checkIn", check_in),
            ("checkOut", check_out),
            ("adults", adults),
            ("rooms", rooms),
            ("children", children),
            ("currency", currency),
            ("limit", 20),
        ]
        for age in child_ages or []:
            params.append(("childAges[]", age))

        response = self._request("/search", params)
        response = self._complete_job_if_needed(response)
        raw_items = response.get("data")
        if not isinstance(raw_items, list):
            raise StayingAPIError("StayingAPI returned an unexpected search response.")

        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        hotels = [
            hotel for item in raw_items
            if isinstance(item, dict)
            if (hotel := self._normalise_hotel(
                item, check_in, check_out, nights, rooms)) is not None
        ]
        return {"hotels": hotels, "meta": response.get("meta", {})}

    def get_reviews(self, platform: str, listing_id: str,
                    limit: int = 10) -> dict[str, Any]:
        """Return real normalized reviews for a selected search result."""
        params = [
            ("platform", platform),
            ("listingId", listing_id),
            ("limit", limit),
        ]
        response = self._complete_job_if_needed(self._request("/reviews", params))
        return {"data": response.get("data"), "meta": response.get("meta", {})}

    def _request(self, path: str, params: list[tuple[str, str | int]]
                 ) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{STAYING_API_BASE_URL}{path}?{query}",
            headers={
                "Accept": "application/json",
                "Authorization": self._auth_header,
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                status = response.status
                retry_after = response.headers.get("Retry-After")
        except urllib.error.HTTPError as error:
            self._raise_http_error(error)
        except (urllib.error.URLError, OSError, TimeoutError,
                json.JSONDecodeError) as error:
            logger.warning("StayingAPI request failed: %s", type(error).__name__)
            raise StayingAPIError(
                "Hotel data is temporarily unavailable. Please try again.") from None
        if not isinstance(payload, dict):
            raise StayingAPIError("StayingAPI returned an unexpected response.")
        payload["_http_status"] = status
        payload["_retry_after"] = retry_after
        if "error" in payload:
            code = self._error_code(payload)
            logger.warning("StayingAPI request rejected: %s", code)
            raise self._safe_provider_error(code)
        return payload

    @classmethod
    def _raise_http_error(cls, error: urllib.error.HTTPError) -> None:
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        code = cls._error_code(payload) if isinstance(payload, dict) else "provider_error"
        logger.warning("StayingAPI returned HTTP %s (%s)", error.code, code)
        raise cls._safe_provider_error(code) from None

    def _complete_job_if_needed(self, response: dict[str, Any]
                                ) -> dict[str, Any]:
        if response.get("_http_status") != 202:
            return response

        job = response.get("data")
        job_id = job.get("jobId") if isinstance(job, dict) else None
        if not isinstance(job_id, str) or not job_id.startswith("job_"):
            raise StayingAPIError("StayingAPI returned an invalid search job.")

        deadline = time.monotonic() + self.max_job_wait
        retry_after = self._retry_delay(response.get("_retry_after"))
        while time.monotonic() < deadline:
            time.sleep(min(retry_after, max(0, deadline - time.monotonic())))
            path = f"/jobs/{urllib.parse.quote(job_id, safe='')}"
            response = self._request(path, [])
            data = response.get("data")
            if not isinstance(data, dict):
                raise StayingAPIError("StayingAPI returned an invalid job status.")
            status = data.get("status")
            if status == "completed":
                result = data.get("result")
                if isinstance(result, dict) and "data" in result:
                    return result
                return {"data": result, "meta": response.get("meta", {})}
            if status == "failed":
                error = data.get("error")
                code = (str(error.get("code") or "job_failed")
                        if isinstance(error, dict) else "job_failed")
                logger.warning("StayingAPI job failed: %s", code)
                raise self._safe_provider_error(code)
            if status not in {"pending", "running"}:
                raise StayingAPIError("StayingAPI returned an unknown job status.")
            retry_after = self._retry_delay(response.get("_retry_after"))

        raise StayingAPIError(
            "Hotel search is taking longer than expected. Please try again.")

    @staticmethod
    def _retry_delay(value: Any) -> float:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return 2.0
        return min(max(seconds, 1.0), 60.0)

    @staticmethod
    def _error_code(response: dict[str, Any]) -> str:
        error = response.get("error")
        return (str(error.get("code") or "provider_error")
                if isinstance(error, dict) else "provider_error")

    @staticmethod
    def _safe_provider_error(code: str) -> StayingAPIError:
        messages = {
            "credit_balance_too_low": "Hotel search credits are unavailable.",
            "insufficient_credits": "Hotel search credits are unavailable.",
            "email_unverified": (
                "Verify the StayingAPI account email before live searches. "
                "Click the one-click link sent at signup (check spam), or "
                "log in at stayingapi.com and resend it from the dashboard."),
            "rate_limit_exceeded": "Hotel search is busy. Please wait and try again.",
        }
        return StayingAPIError(messages.get(
            code, "Hotel data is temporarily unavailable. Please try again."))

    @classmethod
    def _normalise_hotel(cls, item: dict[str, Any], check_in: str,
                         check_out: str, nights: int, rooms: int
                         ) -> dict[str, Any] | None:
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            return None

        location = item.get("location")
        location = location if isinstance(location, dict) else {}
        price = item.get("price")
        price = price if isinstance(price, dict) else {}
        fee_items = price.get("fees")
        fee_items = fee_items if isinstance(fee_items, dict) else {}
        taxes = price.get("taxes")
        if taxes is None:
            taxes = fee_items.get("taxes")
        other_fees = {
            name: amount for name, amount in fee_items.items()
            if name != "taxes" and amount is not None
        }
        guest_rating = item.get("guestRating")
        if guest_rating is None:
            guest_rating = item.get("rating")

        raw_images = item.get("images") or item.get("photos") or []
        if isinstance(raw_images, (str, dict)):
            raw_images = [raw_images]
        images: list[str] = []
        for image in raw_images if isinstance(raw_images, list) else []:
            url = image if isinstance(image, str) else (
                image.get("url") or image.get("src")
                if isinstance(image, dict) else None
            )
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                images.append(url)

        return {
            "hotel_id": item.get("id") or item.get("platformListingId"),
            "platform_listing_id": item.get("platformListingId"),
            "name": name.strip(),
            "description": item.get("description"),
            "location": {
                "city": location.get("city"),
                "region": location.get("region"),
                "country": location.get("country"),
                "address": location.get("address"),
            },
            "images": images,
            "image_url": images[0] if images else None,
            "property_type": item.get("propertyType"),
            "star_rating": item.get("starRating"),
            "rating": guest_rating,
            "rating_scale": item.get("ratingScale"),
            "review_count": item.get("reviewCount"),
            "review_summary": item.get("reviewSummary"),
            "reviews": item.get("reviews") if isinstance(item.get("reviews"), list) else [],
            "amenities": item.get("amenities") if isinstance(item.get("amenities"), list) else [],
            "max_occupancy": item.get("maxOccupancy"),
            "bedrooms": item.get("bedrooms"),
            "bathrooms": item.get("bathrooms"),
            "host": item.get("host"),
            "room_type": item.get("roomType") or item.get("room_type"),
            "bed_type": item.get("bedType") or item.get("bed_type"),
            "availability": item.get("availability"),
            "cancellation_policy": item.get("cancellationPolicy"),
            "booking_url": item.get("url") or price.get("url"),
            "provider": item.get("platform"),
            "price_source": price.get("source"),
            "price_per_night": price.get("nightlyPrice"),
            "total_price": price.get("totalPrice"),
            "taxes": taxes,
            "fees": other_fees or None,
            "currency": price.get("currency"),
            "nights": price.get("nights") or nights,
            "rooms": rooms,
            "dates": {"check_in": check_in, "check_out": check_out},
        }
