/* Wize front-end behaviour (progressive enhancement only).
 *
 * The server renders complete HTML; this file only adds confirmations for
 * destructive actions and a small helper for the JSON API.
 */
(function () {
  "use strict";

  // Confirm before destructive submits (data-confirm="...").
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form && form.dataset && form.dataset.confirm) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    }
  });

  // Fetch the CSRF token from the page so API calls can authenticate.
  function csrfToken() {
    var field = document.querySelector('input[name="csrf_token"]');
    return field ? field.value : "";
  }

  // Small JSON helper for future fetch-based UI enhancements.
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