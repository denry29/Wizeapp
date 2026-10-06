"""Destination routes: catalogue browsing plus trip attachment."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import (Blueprint, Response, current_app, jsonify, redirect,
                   render_template, request, session, url_for)

from managers.base_manager import NotFoundError
from services import validation
from services.commons import USER_AGENT
from services.security import (api_error, csrf_protect, current_user_id,
                               login_required)

destinations_bp = Blueprint("destinations", __name__)
MAX_DESTINATION_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_DESTINATION_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _manager():
    return current_app.extensions["managers"]["destinations"]


def _filters() -> dict[str, Any]:
    """Read the browse/filter query-string parameters."""
    return {
        "search": validation.clean_optional(request.args.get("search") or request.args.get("q"), 80),
        "country": validation.clean_optional(request.args.get("country"), 60),
        "city": validation.clean_optional(request.args.get("city"), 60),
        "category": validation.optional_choice(
            request.args.get("category"),
            current_app.config["DESTINATION_CATEGORIES"]),
    }


# --------------------------------------------------------------- JSON API --
@destinations_bp.route("/api/destinations", methods=["GET"])
@destinations_bp.route("/api/destinations/search", methods=["GET"])
def api_search():
    """GET /api/destinations?search=&country=&city=&category=&page=

    Public endpoint: the catalogue is shared reference data, not personal data.
    """
    try:
        result = _manager().search_catalogue(
            **_filters(),
            page=validation.positive_int(request.args.get("page", 1), "page"),
            per_page=min(int(request.args.get("per_page", current_app.config["ITEMS_PER_PAGE"])), 100),
        )
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({
        "destinations": [item.serialize() for item in result["items"]],
        "pagination": {k: v for k, v in result.items() if k != "items"},
        "filters": _filters(),
    })


@destinations_bp.route("/api/destinations/filters", methods=["GET"])
def api_filter_options():
    """Countries / categories available for the filter controls."""
    manager = _manager()
    country = validation.clean_optional(request.args.get("country"), 60)
    return jsonify({
        "countries": manager.distinct_countries(),
        "categories": list(current_app.config["DESTINATION_CATEGORIES"]),
        "cities": manager.cities_for_country(country) if country else [],
        "total": manager.catalogue_total(),
    })


@destinations_bp.route("/api/destinations/<int:destination_id>", methods=["GET"])
def api_detail(destination_id: int):
    """GET /api/destinations/<id>"""
    try:
        destination = _manager().get_catalogue_destination(destination_id)
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"destination": destination.serialize()})


@destinations_bp.route("/api/destinations/<int:destination_id>/image",
                       methods=["GET"])
def api_destination_image(destination_id: int):
    """Serve a catalogue photo through the backend for mobile clients."""
    try:
        destination = _manager().get_catalogue_destination(destination_id)
    except Exception as error:                       # noqa: BLE001
        return api_error(error)

    image_url = destination.serialize().get("image_url")
    parsed_url = urllib.parse.urlsplit(image_url or "")
    if (parsed_url.scheme != "https"
            or parsed_url.hostname != "upload.wikimedia.org"):
        return jsonify({"error": "No Wikimedia photo is available."}), 404

    image_request = urllib.request.Request(
        image_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/jpeg,image/png,image/webp",
        },
    )
    try:
        with urllib.request.urlopen(image_request, timeout=15) as upstream:
            final_url = urllib.parse.urlsplit(upstream.geturl())
            if (final_url.scheme != "https"
                    or final_url.hostname != "upload.wikimedia.org"):
                return jsonify({"error": "Wikimedia returned an invalid image URL."}), 502

            content_type = upstream.headers.get_content_type()
            if content_type not in ALLOWED_DESTINATION_IMAGE_TYPES:
                return jsonify({"error": "Wikimedia did not return an image."}), 502

            image_data = upstream.read(MAX_DESTINATION_IMAGE_BYTES + 1)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        current_app.logger.warning(
            "Wikimedia photo request failed for destination %s: %s",
            destination_id, error)
        return jsonify({"error": "Destination photo could not be loaded."}), 502

    if not image_data or len(image_data) > MAX_DESTINATION_IMAGE_BYTES:
        return jsonify({"error": "Wikimedia image exceeds the allowed size."}), 502

    return Response(image_data, mimetype=content_type)


@destinations_bp.route("/api/trips/<int:trip_id>/destinations", methods=["GET"])
@login_required
def api_list_for_trip(trip_id: int):
    """Destinations attached to one of the caller's trips."""
    user_id = current_user_id()
    try:
        current_app.extensions["managers"]["trips"].get_by_id(trip_id, user_id)
        items = _manager().list_for_trip(trip_id)
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"destinations": [item["payload"] for item in items]})


@destinations_bp.route("/api/trips/<int:trip_id>/destinations", methods=["POST"])
@login_required
@csrf_protect
def api_attach(trip_id: int):
    """POST - add a catalogue destination or a custom one to a trip."""
    try:
        result = _manager().attach_to_trip(
            trip_id, current_user_id(), validation.get_request_payload(request))
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Destination added to trip.",
                    "destination": result["destination"].serialize(),
                    "trip_destination_id": result["trip_destination_id"]}), 201


@destinations_bp.route("/api/trips/<int:trip_id>/destinations/<int:link_id>",
                       methods=["PATCH", "PUT"])
@login_required
@csrf_protect
def api_update_link(trip_id: int, link_id: int):
    """PATCH - change the visit date, notes or order of an attached destination."""
    try:
        result = _manager().update_trip_link(
            trip_id, link_id, current_user_id(),
            validation.get_request_payload(request))
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Trip destination updated.", **result})


@destinations_bp.route("/api/trips/<int:trip_id>/destinations/<int:link_id>",
                       methods=["DELETE"])
@login_required
@csrf_protect
def api_detach(trip_id: int, link_id: int):
    """DELETE - remove a destination from the trip (the catalogue entry stays)."""
    try:
        _manager().detach_from_trip(trip_id, link_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Destination removed from trip."})


# ------------------------------------------------------------ HTML pages ---
@destinations_bp.route("/destinations")
def browse():
    """Searchable, filterable catalogue of the predefined Asian attractions."""
    manager = _manager()
    filters = _filters()
    result = manager.search_catalogue(**filters, page=1,
                                      per_page=current_app.config["ITEMS_PER_PAGE"])
    return render_template(
        "destinations/list.html", destinations=result["items"],
        pagination=result, filters=filters,
        countries=manager.distinct_countries(),
        cities=manager.cities_for_country(filters["country"]) if filters["country"] else [],
        categories=current_app.config["DESTINATION_CATEGORIES"],
        total=manager.catalogue_total(),
        page_title="Browse Asian destinations")


@destinations_bp.route("/destinations/<int:destination_id>")
def detail(destination_id: int):
    """Detail page; signed-in visitors also get the 'add to trip' control."""
    try:
        destination = _manager().get_catalogue_destination(destination_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Destination not found"), 404

    trips = []
    if session.get("user_id"):
        trips = current_app.extensions["managers"]["trips"].list_for_user(
            current_user_id())
    return render_template("destinations/detail.html", destination=destination,
                           trips=trips, page_title=destination.name)


@destinations_bp.route("/trips/<int:trip_id>/destinations/add", methods=["POST"])
@login_required
@csrf_protect
def add_to_trip(trip_id: int):
    """HTML form handler used by the destination detail page."""
    try:
        _manager().attach_to_trip(trip_id, current_user_id(),
                                  validation.get_request_payload(request))
    except validation.ValidationError as error:
        return render_template("errors/404.html", page_title=error.message), 400
    except NotFoundError:
        return render_template("errors/404.html", page_title="Trip not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@destinations_bp.route("/trips/<int:trip_id>/destinations/<int:link_id>/remove",
                       methods=["POST"])
@login_required
@csrf_protect
def remove_from_trip(trip_id: int, link_id: int):
    try:
        _manager().detach_from_trip(trip_id, link_id, current_user_id())
    except NotFoundError:
        return render_template("errors/404.html", page_title="Not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))
