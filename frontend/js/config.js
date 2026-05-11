/**
 * Single place for frontend configuration.
 * - On localhost: uses http://127.0.0.1:8000 (local backend).
 * - On server: uses same origin + /api (Nginx proxies /api to backend).
 * Override by setting window.APP_CONFIG.API_BASE_URL before this script runs.
 */
(function() {
  var base = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL);
  if (!base) {
    var isLocal = /^(localhost|127\.0\.0\.1)$/.test(window.location.hostname);
    base = isLocal ? "http://127.0.0.1:8000" : (window.location.origin + "/api");
  }
  window.APP_CONFIG = window.APP_CONFIG || {};
  window.APP_CONFIG.API_BASE_URL = base.replace(/\/$/, "");
})();
