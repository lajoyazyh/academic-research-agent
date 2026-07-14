(function () {
  "use strict";

  var auth = window.academicAuth;
  if (!auth || !auth.configured || !auth.client) return;

  auth.client.auth.getSession().then(function (result) {
    if (!result.data || !result.data.session) return;
    var destinations = ["marketPrimaryLink", "marketHeroCta", "marketBottomCta"];
    destinations.forEach(function (id) {
      var link = document.getElementById(id);
      if (!link) return;
      link.href = "/app";
      link.textContent = id === "marketBottomCta" ? "进入我的研究空间" : "进入研究工作台";
    });
    var loginLink = document.getElementById("marketLoginLink");
    if (loginLink) {
      loginLink.href = "/app/profile";
      loginLink.textContent = "个人中心";
    }
  });
})();
