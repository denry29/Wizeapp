"""Wize - Trip Planner (Flask application factory)."""

from __future__ import annotations

import os
from pathlib import Path

from flask import (Flask, jsonify, render_template, request, send_from_directory,
                   session)

from config import get_config
from database.db import DatabaseManager, register_cli
from managers.auth_manager import AuthManager
from managers.checklist_manager import ChecklistManager
from managers.dashboard_manager import DashboardManager
from managers.destination_manager import DestinationManager
from managers.expense_manager import ExpenseManager
from managers.schedule_manager import ScheduleManager
from managers.trip_manager import TripManager
from routes.auth_routes import auth_bp
from routes.checklist_routes import checklists_bp
from routes.dashboard_routes import dashboard_bp
from routes.destination_routes import destinations_bp
from routes.expense_routes import expenses_bp
from routes.hotel_routes import hotels_bp
from routes.mobile_routes import mobile_bp
from routes.schedule_routes import schedules_bp
from routes.trip_routes import trips_bp
from services.security import generate_csrf_token


def create_app(config_name: str | None = None,
               database_path: Path | str | None = None) -> Flask:
    """Build and configure the Flask application.

    The factory pattern keeps the app testable: tests create an isolated app
    with its own database instead of importing a global instance.  Pass
    ``database_path`` to override where the SQLite file lives.
    """
    app = Flask(__name__, instance_relative_config=False)
    config_class = get_config(config_name)
    app.config.from_object(config_class)
    if database_path is not None:
        app.config["DATABASE_PATH"] = Path(database_path)
    config_class.init_app(app)

    # ---------------------------------------------------------- database ----
    db = DatabaseManager(app.config["DATABASE_PATH"], app.config["SCHEMA_PATH"])
    db.init_app(app)
    register_cli(app)

    # ----------------------------------------------------------- managers ---
    # One instance of each manager per app; they share the DatabaseManager.
    app.extensions["managers"] = {
        "auth": AuthManager(db),
        "trips": TripManager(db),
        "destinations": DestinationManager(db),
        "schedules": ScheduleManager(db),
        "expenses": ExpenseManager(db),
        "checklists": ChecklistManager(db),
        "dashboard": DashboardManager(db),
    }

    # ------------------------------------------------------------ routing ---
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(trips_bp)
    app.register_blueprint(destinations_bp)
    app.register_blueprint(schedules_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(hotels_bp)
    app.register_blueprint(checklists_bp)
    app.register_blueprint(mobile_bp)

    # ------------------------------------------------------ security hooks ---
    @app.before_request
    def ensure_csrf_token() -> None:
        """Every session gets a CSRF token for the forms it renders."""
        generate_csrf_token()

    @app.after_request
    def add_security_headers(response):
        """Baseline browser security headers."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' https: data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'")
        if request.path.startswith("/api/"):
            if request.endpoint == "destinations.api_destination_image":
                response.headers.setdefault("Cache-Control", "public, max-age=86400")
            else:
                response.headers["Cache-Control"] = "no-store"
            origin = request.headers.get("Origin")
            if origin in app.config["EXPO_WEB_ORIGINS"]:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = (
                    "GET, POST, PUT, PATCH, DELETE, OPTIONS")
                response.headers["Access-Control-Allow-Headers"] = (
                    "Content-Type, X-CSRF-Token")
                response.headers.add("Vary", "Origin")
        return response

    # ------------------------------------------------------ error handlers ---
    @app.errorhandler(400)
    def bad_request(error):
        if _wants_json():
            return jsonify({"error": getattr(error, "description", "Bad request")}), 400
        return render_template("errors/400.html",
                               message=getattr(error, "description", None)), 400

    @app.errorhandler(404)
    def not_found(error):
        if _wants_json():
            return jsonify({"error": "Resource not found."}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):                    # pragma: no cover - safety net
        app.logger.exception("Internal server error: %s", error)
        if _wants_json():
            return jsonify({"error": "Internal server error."}), 500
        return render_template("errors/500.html"), 500

    @app.context_processor
    def inject_globals() -> dict:
        """Values every template needs (CSRF token + current user id)."""
        return {
            "csrf_token": generate_csrf_token,
            "current_user_id": session.get("user_id"),
            "is_authenticated": bool(session.get("user_id")),
        }

    # ---------------------------------------------------------- pwa / icons --
    @app.route("/manifest.webmanifest")
    def web_manifest():
        """Serve the web app manifest with the content type browsers expect.

        ``mimetypes`` does not know the ``.webmanifest`` extension on every
        platform, so the type is stated explicitly instead of guessed.
        """
        return send_from_directory(app.static_folder, "manifest.webmanifest",
                                   mimetype="application/manifest+json")

    @app.route("/health")
    def health():
        """Simple liveness probe that also confirms the DB is reachable."""
        try:
            tables = len(db.table_names())
            return jsonify({"status": "ok", "database": str(db.database_path),
                            "tables": tables}), 200
        except Exception as error:               # noqa: BLE001
            return jsonify({"status": "error", "detail": str(error)}), 503

    return app


def _wants_json() -> bool:
    return (request.is_json or request.path.startswith("/api/")
            or request.accept_mimetypes.best == "application/json")


app = create_app(os.environ.get("WIZE_ENV"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=app.config.get("DEBUG", False))