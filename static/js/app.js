/* Wize front-end extras.
 *
 * The server already renders the page. This file just confirms risky actions
 * and gives the page a small helper for JSON API requests.
 */
(function () {
  "use strict";

  // Ask before submitting a form marked as a destructive action.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form && form.dataset && form.dataset.confirm) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    }
  });

  // Grab the CSRF token from the page for API requests.
  function csrfToken() {
    var field = document.querySelector('input[name="csrf_token"]');
    return field ? field.value : "";
  }

  // Keep JSON requests in one place so the page can reuse the same setup.
  window.Wize = {
    csrfToken: csrfToken,

    async request(url, options) {
      var settings = Object.assign({ credentials: "same-origin" }, options || {});
      settings.headers = Object.assign(
        { "X-CSRF-Token": csrfToken(), "Accept": "application/json" },
        settings.headers || {}
      );
      if (settings.body && typeof settings.body !== "string") {
        settings.headers["Content-Type"] = "application/json";
        settings.body = JSON.stringify(settings.body);
      }
      var response = await fetch(url, settings);
      var payload = null;
      try {
        payload = await response.json();
      } catch (error) {
        payload = null;
      }
      return { ok: response.ok, status: response.status, data: payload };
    }
  };
})();