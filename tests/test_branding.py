"""App branding tests: logo, favicon, PWA manifest and home-screen metadata.

The logo the user sees on their phone lives in three separate places, and each
one has its own failure mode, so all three are asserted here:

* the browser tab          -> ``favicon.ico`` / ``favicon-32.png``
* the iOS home screen      -> ``apple-touch-icon.png`` (opaque PNG, 180x180)
* the Android home screen  -> ``manifest.webmanifest`` icons

Plus the in-app header logo and the meta tags that let a phone install the
site as a standalone app.
"""

from __future__ import annotations

import json

import pytest

#: Icon files that must exist in ``static/`` for the phone branding to work.
ICON_FILES = [
    "favicon.ico",
    "favicon-32.png",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
    "logo-160.png",
]

#: ``<meta>`` tags a phone needs before "Add to Home Screen" is offered.
REQUIRED_META = [
    'name="theme-color"',
    'name="apple-mobile-web-app-capable"',
    'name="apple-mobile-web-app-title"',
    'name="mobile-web-app-capable"',
]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture()
def manifest(client):
    """The parsed ``/manifest.webmanifest`` document."""
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    return json.loads(response.data)


# ---------------------------------------------------------------- static icons --
@pytest.mark.parametrize("filename", ICON_FILES)
def test_icon_is_served(client, filename):
    response = client.get(f"/static/{filename}")
    assert response.status_code == 200
    assert len(response.data) > 0, f"{filename} is empty"


@pytest.mark.parametrize("filename", [f for f in ICON_FILES if f.endswith(".png")])
def test_png_icons_have_a_valid_signature(client, filename):
    assert client.get(f"/static/{filename}").data.startswith(PNG_MAGIC)


def test_favicon_is_a_real_multi_resolution_ico(client):
    """ICONDIR: reserved=0, type=1 (icon), count = number of embedded frames."""
    data = client.get("/static/favicon.ico").data
    assert int.from_bytes(data[0:2], "little") == 0        # reserved
    assert int.from_bytes(data[2:4], "little") == 1        # type: icon
    assert int.from_bytes(data[4:6], "little") >= 2        # 16/32/48 frames


def test_apple_touch_icon_is_opaque(client):
    """iOS renders alpha in apple-touch-icon.png as solid black, so ban it.

    A real PNG colour type of 2 (truecolour) or 3 (palette) carries no alpha;
    types 4 and 6 do.
    """
    data = client.get("/static/apple-touch-icon.png").data
    # IHDR colour type lives at byte 25 of the PNG payload.
    assert data[25] in (2, 3), "apple-touch-icon.png must not have an alpha channel"


# ------------------------------------------------------------------- manifest --
def test_manifest_is_served_with_the_expected_content_type(client):
    response = client.get("/manifest.webmanifest")
    assert response.headers["Content-Type"] == "application/manifest+json"


def test_manifest_describes_a_standalone_app(manifest):
    assert manifest["display"] == "standalone"
    assert manifest["name"].startswith("Wize")
    assert manifest["short_name"] == "Wize"
    assert manifest["start_url"] == "/"


def test_manifest_theme_colour_matches_the_header_meta(client, manifest):
    page = client.get("/auth/login").get_data(as_text=True)
    assert f'content="{manifest["theme_color"]}"' in page


def test_manifest_includes_a_maskable_icon(manifest):
    """Android crops 'any' icons with a launcher mask; 'maskable' ones survive it."""
    purposes = {icon.get("purpose") for icon in manifest["icons"]}
    assert "maskable" in purposes


def test_manifest_declares_the_standard_pwa_sizes(manifest):
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes


def test_every_manifest_icon_actually_resolves(client, manifest):
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200, icon["src"]


# --------------------------------------------------------------- page metadata --
def test_pages_link_every_icon_they_need(client):
    page = client.get("/auth/login").get_data(as_text=True)
    assert 'rel="icon"' in page
    assert "favicon.ico" in page
    assert 'rel="apple-touch-icon"' in page
    assert 'rel="manifest"' in page


@pytest.mark.parametrize("needle", REQUIRED_META)
def test_pages_include_the_home_screen_meta_tags(client, needle):
    assert needle in client.get("/auth/login").get_data(as_text=True)


def test_header_shows_the_logo_image(client):
    page = client.get("/auth/login").get_data(as_text=True)
    assert 'class="brand-logo"' in page
    assert "logo-160.png" in page


def test_old_text_placeholder_logo_is_gone(client):
    page = client.get("/auth/login").get_data(as_text=True)
    assert "brand-mark" not in page


def test_content_security_policy_still_allows_the_local_images(client):
    csp = client.get("/auth/login").headers["Content-Security-Policy"]
    assert "img-src 'self'" in csp
