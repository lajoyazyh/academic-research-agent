(function () {
  "use strict";

  var auth = window.academicAuth;
  var apiKey = document.getElementById("providerApiKey");
  var baseUrl = document.getElementById("providerBaseUrl");
  var model = document.getElementById("providerModel");
  var status = document.getElementById("apiStatus");
  var message = document.getElementById("apiMessage");
  var defaults = {
    base_url: "https://open.bigmodel.cn/api/paas/v4/",
    model: "glm-4-flash"
  };
  var user = null;

  function storageKey() {
    return "academic-agent:provider:" + (user ? user.id : "local");
  }

  function showMessage(text, type) {
    message.textContent = text || "";
    message.className = "form-message" + (text ? " visible " + (type || "success") : "");
  }

  function setStatus(text, kind, icon) {
    status.className = "api-status" + (kind ? " " + kind : "");
    status.innerHTML = '<i class="fa-solid ' + icon + '"></i><span></span>';
    status.querySelector("span").textContent = text;
  }

  function loadLocalConfig() {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(storageKey()) || "{}"); } catch (_error) { saved = {}; }
    apiKey.value = saved.api_key || "";
    baseUrl.value = saved.base_url || defaults.base_url;
    model.value = saved.model || defaults.model;
    if (apiKey.value) setStatus("已在当前浏览器配置 API Key。", "ok", "fa-circle-check");
    else setStatus("尚未配置 API Key，AI 生成功能可能无法使用。", "warn", "fa-triangle-exclamation");
  }

  async function checkServerDefaults() {
    try {
      var response = await fetch("/api/provider/status");
      if (!response.ok) return;
      var data = await response.json();
      if (!baseUrl.value && data.default_base_url) baseUrl.value = data.default_base_url;
      if (!model.value && data.default_model) model.value = data.default_model;
      if (!apiKey.value && data.server_provider_available) {
        setStatus("服务端存在备用模型配置；公共服务仍建议使用你自己的 API Key。", "ok", "fa-circle-info");
      }
    } catch (_error) {
      if (!apiKey.value) setStatus("暂时无法检查服务端状态，你仍可保存自己的 API 配置。", "warn", "fa-triangle-exclamation");
    }
  }

  if (!auth || !auth.configured || !auth.client) return;

  (window.academicAuthReady || auth.client.auth.getSession().then(function (result) { return result.data.session; }))
    .then(function (session) {
      if (!session || !session.user) return;
      user = session.user;
      var email = String(user.email || "用户");
      var displayName = user.user_metadata && user.user_metadata.display_name;
      document.getElementById("profileAvatar").textContent = email.charAt(0).toUpperCase();
      document.getElementById("profileEmail").textContent = displayName || email;
      document.getElementById("profileMeta").textContent = displayName ? email : "已安全登录";
      loadLocalConfig();
      checkServerDefaults();
    });

  document.getElementById("apiKeyToggle").addEventListener("click", function () {
    var visible = apiKey.type === "text";
    apiKey.type = visible ? "password" : "text";
    this.setAttribute("aria-label", visible ? "显示 API Key" : "隐藏 API Key");
    this.innerHTML = visible ? '<i class="fa-regular fa-eye"></i>' : '<i class="fa-regular fa-eye-slash"></i>';
  });

  document.getElementById("apiForm").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!user) return;
    var value = {
      api_key: apiKey.value.trim(),
      base_url: baseUrl.value.trim() || defaults.base_url,
      model: model.value.trim() || defaults.model,
      save_local: true
    };
    try {
      new URL(value.base_url);
    } catch (_error) {
      showMessage("Base URL 格式无效，请填写完整的 http:// 或 https:// 地址。", "error");
      return;
    }
    localStorage.setItem(storageKey(), JSON.stringify(value));
    setStatus(value.api_key ? "已在当前浏览器配置 API Key。" : "配置已保存，但 API Key 仍为空。", value.api_key ? "ok" : "warn", value.api_key ? "fa-circle-check" : "fa-triangle-exclamation");
    showMessage("配置已保存。返回控制台后即可使用。", "success");
  });

  document.getElementById("clearApiButton").addEventListener("click", function () {
    if (!user) return;
    localStorage.removeItem(storageKey());
    apiKey.value = "";
    baseUrl.value = defaults.base_url;
    model.value = defaults.model;
    setStatus("本地 API 配置已清除。", "warn", "fa-triangle-exclamation");
    showMessage("已从当前浏览器清除 API 配置。", "success");
  });

  document.getElementById("signOutButton").addEventListener("click", async function () {
    this.disabled = true;
    await auth.client.auth.signOut();
    window.location.replace("/auth");
  });
})();
