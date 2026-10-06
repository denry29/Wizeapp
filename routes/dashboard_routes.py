"""Dashboard routes."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template

from services.security import current_user_id, login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/dashboard")
@login_required
def api_summary():
    """GET /api/dashboard - overview for the signed-in user only."""
    summary = current_app.extensions["managers"]["dashboard"].summary(current_user_id())
    return jsonify(summary)


@dashboard_bp.route("/dashboard")
@dashboard_bp.route("/")
@login_required
def index():
    """HTML dashboard page."""
    summary = current_app.extensions["managers"]["dashboard"].summary(current_user_id())
    return render_template("dashboard.html", summary=summary,
                           page_title="Dashboard")