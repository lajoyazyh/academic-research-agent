(function () {
  "use strict";

  var allowed = new Set([
    "signup_completed",
    "provider_test_succeeded",
    "project_created",
    "first_search_completed",
    "first_review_generated"
  ]);

  window.va = window.va || function () {
    (window.vaq = window.vaq || []).push(arguments);
  };
  window.academicTrack = function (name) {
    if (!allowed.has(name)) return;
    // Deliberately send only the event name: never research text, paper data,
    // repository names, account identifiers, or model credentials.
    window.va("event", { name: name });
  };

  if (!/^(localhost|127\.0\.0\.1)$/.test(window.location.hostname)) {
    var script = document.createElement("script");
    script.defer = true;
    script.src = "/_vercel/insights/script.js";
    document.head.appendChild(script);
  }
})();
