(function () {
  "use strict";

  var auth = window.academicAuth;
  if (!auth || !auth.configured || !auth.client) {
    window.academicAuthReady = Promise.resolve(null);
    return;
  }

  var currentPath = window.location.pathname + window.location.search + window.location.hash;

  function authUrl() {
    return "/auth?next=" + encodeURIComponent(currentPath);
  }

  function redirectToAuth() {
    if (window.location.pathname !== "/auth") {
      window.location.replace(authUrl());
    }
  }

  function addAccountLink(user) {
    if (!user || document.querySelector("[data-account-link]")) return;
    var container = document.querySelector(".topbar-right");
    if (!container) return;

    var email = String(user.email || "用户");
    var initial = email.charAt(0).toUpperCase();
    var link = document.createElement("a");
    link.href = "/app/profile";
    link.className = "ghost-btn account-nav-btn";
    link.dataset.accountLink = "true";
    link.title = email;
    link.innerHTML = '<span class="account-nav-avatar" aria-hidden="true"></span><span>个人中心</span>';
    link.querySelector(".account-nav-avatar").textContent = initial;
    container.appendChild(link);
  }

  function publishSession(session) {
    var user = session && session.user ? session.user : null;
    window.academicAuthUserId = user ? user.id : "anonymous";
    window.academicAuthSession = session || null;
    if (user) addAccountLink(user);
    window.dispatchEvent(new CustomEvent("academic-auth-changed", {
      detail: { userId: window.academicAuthUserId, user: user }
    }));
    return session || null;
  }

  window.academicAuthRequireLogin = redirectToAuth;
  window.academicAuthReady = auth.client.auth.getSession().then(function (result) {
    var session = result.data && result.data.session;
    publishSession(session);
    if (!session) redirectToAuth();
    return session || null;
  }).catch(function () {
    redirectToAuth();
    return null;
  });

  auth.client.auth.onAuthStateChange(function (event, session) {
    publishSession(session);
    if (event === "SIGNED_OUT" || !session) redirectToAuth();
  });
})();
