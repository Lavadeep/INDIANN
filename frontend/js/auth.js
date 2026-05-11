/**
 * Auth helpers: current user from localStorage, redirect if not logged in.
 * Use after config.js. On protected pages call requireAuth() at script start.
 */
(function () {
  function getCurrentUser() {
    try {
      const raw = localStorage.getItem("user");
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function requireAuth() {
    const user = getCurrentUser();
    if (!user || !user.user_id) {
      window.location.href = "login.html";
      return null;
    }
    return user;
  }

  window.getCurrentUser = getCurrentUser;
  window.requireAuth = requireAuth;
})();
