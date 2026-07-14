(function () {
  "use strict";

  var config = window.ACADEMIC_AGENT_CONFIG || {};
  var apiBase = String(config.apiBaseUrl || "").replace(/\/$/, "");
  var originalFetch = window.fetch.bind(window);
  var client = null;

  if (config.supabaseUrl && config.supabaseAnonKey && window.supabase) {
    client = window.supabase.createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
    });
    // Register immediately so OAuth provider tokens are captured during the
    // callback event. They remain session-scoped and are never persisted with
    // research data or the long-lived Supabase session.
    client.auth.onAuthStateChange(function (event, session) {
      if (session && session.user && session.provider_token) {
        sessionStorage.setItem("academic-agent:github-token:" + session.user.id, session.provider_token);
      }
      if (event === "SIGNED_OUT") {
        Object.keys(sessionStorage).forEach(function (key) {
          if (key.indexOf("academic-agent:github-token:") === 0) sessionStorage.removeItem(key);
        });
      }
    });
  }
  window.academicAuth = { client: client, configured: Boolean(client) };

  window.fetch = async function (input, init) {
    var requestInit = Object.assign({}, init || {});
    var rawUrl = typeof input === "string" ? input : input.url;
    var isAgentApi = rawUrl.indexOf("/api/") === 0;

    if (isAgentApi && apiBase) {
      input = apiBase + rawUrl;
    }
    if (isAgentApi && client) {
      var result = await client.auth.getSession();
      var session = result.data && result.data.session;
      var headers = new Headers(requestInit.headers || (typeof input !== "string" ? input.headers : undefined));
      if (session && session.access_token) {
        headers.set("Authorization", "Bearer " + session.access_token);
      }
      requestInit.headers = headers;
    }
    var response = await originalFetch(input, requestInit);
    if (isAgentApi && response.status === 401 && window.academicAuthRequireLogin) {
      window.academicAuthRequireLogin();
    }
    return response;
  };
})();
