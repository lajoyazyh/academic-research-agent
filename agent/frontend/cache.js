(function () {
  "use strict";

  var PREFIX = "academic-agent:cache:v2:";

  function storage(kind) {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  }

  async function scope() {
    if (!window.academicAuth || !window.academicAuth.configured) return "local";
    if (window.academicAuthUserId && window.academicAuthUserId !== "anonymous") {
      return window.academicAuthUserId;
    }
    try {
      await Promise.race([
        window.academicAuthReady || Promise.resolve(null),
        new Promise(function (resolve) { setTimeout(resolve, 1500); })
      ]);
    } catch (_error) {
      return null;
    }
    return window.academicAuthUserId && window.academicAuthUserId !== "anonymous"
      ? window.academicAuthUserId
      : null;
  }

  function cacheKey(userScope, namespace, id) {
    return PREFIX + encodeURIComponent(userScope) + ":" + namespace + ":" + (id || "default");
  }

  async function getEntry(namespace, id, options) {
    var userScope = await scope();
    if (!userScope) return null;
    var kind = options && options.storage === "local" ? "local" : "session";
    try {
      var raw = storage(kind).getItem(cacheKey(userScope, namespace, id));
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      var ageMs = Math.max(0, Date.now() - Number(parsed.saved_at || 0));
      var maxAgeMs = Number(options && options.maxAgeMs || 0);
      if (maxAgeMs > 0 && ageMs > maxAgeMs) {
        storage(kind).removeItem(cacheKey(userScope, namespace, id));
        return null;
      }
      return { value: parsed.value, ageMs: ageMs, savedAt: parsed.saved_at };
    } catch (_error) {
      return null;
    }
  }

  async function set(namespace, id, value, options) {
    var userScope = await scope();
    if (!userScope) return;
    var kind = options && options.storage === "local" ? "local" : "session";
    try {
      var targetKey = cacheKey(userScope, namespace, id);
      if (kind === "session" && namespace === "session") {
        var sessionPrefix = PREFIX + encodeURIComponent(userScope) + ":session:";
        Object.keys(sessionStorage).forEach(function (key) {
          if (key.indexOf(sessionPrefix) === 0 && key !== targetKey) sessionStorage.removeItem(key);
        });
      }
      storage(kind).setItem(targetKey, JSON.stringify({
        saved_at: Date.now(),
        value: value
      }));
    } catch (_error) {
      // Storage can be unavailable or full. Caching must never block research.
    }
  }

  async function remove(namespace, id, options) {
    var userScope = await scope();
    if (!userScope) return;
    var kind = options && options.storage === "local" ? "local" : "session";
    try { storage(kind).removeItem(cacheKey(userScope, namespace, id)); } catch (_error) {}
  }

  function clearScope(userScope) {
    if (!userScope || userScope === "anonymous") return;
    var prefix = PREFIX + encodeURIComponent(userScope) + ":";
    try {
      Object.keys(sessionStorage).forEach(function (key) {
        if (key.indexOf(prefix) === 0) sessionStorage.removeItem(key);
      });
    } catch (_error) {}
  }

  window.academicCache = {
    getEntry: getEntry,
    set: set,
    remove: remove,
    scope: scope,
    clearScope: clearScope
  };
})();
