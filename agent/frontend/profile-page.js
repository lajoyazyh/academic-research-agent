(function () {
  "use strict";

  var auth = window.academicAuth;
  var apiKey = document.getElementById("providerApiKey");
  var providerSelect = document.getElementById("providerSelect");
  var providerDescription = document.getElementById("providerDescription");
  var baseUrl = document.getElementById("providerBaseUrl");
  var chatModel = document.getElementById("providerModel");
  var customChatModel = document.getElementById("providerCustomModel");
  var embeddingModel = document.getElementById("providerEmbeddingModel");
  var customEmbeddingModel = document.getElementById("providerCustomEmbeddingModel");
  var remember = document.getElementById("providerRemember");
  var advanced = document.getElementById("providerAdvanced");
  var status = document.getElementById("apiStatus");
  var message = document.getElementById("apiMessage");
  var testButton = document.getElementById("testApiButton");
  var saveButton = document.getElementById("saveApiButton");
  var catalog = [];
  var user = null;
  var githubConnection = document.getElementById("githubConnection");
  var connectGithubButton = document.getElementById("connectGithubButton");

  function githubHeaders() {
    return window.academicGitHubHeaders ? window.academicGitHubHeaders() : {};
  }

  async function refreshGithubStatus() {
    if (!githubConnection || !connectGithubButton) return;
    var token = window.academicGitHubToken ? window.academicGitHubToken() : "";
    if (!token) {
      githubConnection.className = "github-connection warn";
      githubConnection.innerHTML = '<span class="github-connection-icon"><i class="fa-solid fa-link-slash"></i></span><span><strong>尚未连接</strong><small>连接时会请求仓库读写权限，用于检索与导出。</small></span>';
      connectGithubButton.innerHTML = '<i class="fa-brands fa-github"></i> 前往 GitHub 授权';
      return;
    }
    try {
      var response = await fetch("/api/github/status", { headers: githubHeaders() });
      var data = await response.json();
      if (!data.connected) throw new Error("not connected");
      githubConnection.className = "github-connection ok";
      githubConnection.innerHTML = '<span class="github-connection-icon"><i class="fa-solid fa-circle-check"></i></span><span><strong>@' + String(data.login || "GitHub") + '</strong><small>已可调研仓库并导出研究产物。</small></span>';
      connectGithubButton.innerHTML = '<i class="fa-solid fa-rotate"></i> 重新授权';
    } catch (_error) {
      githubConnection.className = "github-connection warn";
      githubConnection.innerHTML = '<span class="github-connection-icon"><i class="fa-solid fa-triangle-exclamation"></i></span><span><strong>授权需要更新</strong><small>重新连接后即可继续使用仓库功能。</small></span>';
      connectGithubButton.innerHTML = '<i class="fa-brands fa-github"></i> 重新连接';
    }
  }

  var fallbackCatalog = [
    {
      id: "zhipu",
      name: "智谱 AI",
      description: "当前项目默认支持，适合中文学术研究。",
      base_url: "https://open.bigmodel.cn/api/paas/v4/",
      chat_models: ["glm-4-flash", "glm-4-plus"],
      default_chat_model: "glm-4-flash",
      embedding_models: ["embedding-3", "embedding-2"],
      default_embedding_model: "embedding-3"
    },
    {
      id: "openai",
      name: "OpenAI",
      description: "使用 OpenAI 官方 API。",
      base_url: "https://api.openai.com/v1/",
      chat_models: ["gpt-5-mini", "gpt-4.1-mini"],
      default_chat_model: "gpt-5-mini",
      embedding_models: ["text-embedding-3-small", "text-embedding-3-large"],
      default_embedding_model: "text-embedding-3-small"
    },
    {
      id: "custom",
      name: "自定义 OpenAI-compatible",
      description: "高级选项；需要自行确认聊天和向量接口兼容性。",
      base_url: "",
      chat_models: [],
      default_chat_model: "",
      embedding_models: [],
      default_embedding_model: ""
    }
  ];

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

  function currentProvider() {
    return catalog.find(function (item) { return item.id === providerSelect.value; }) || catalog[0] || fallbackCatalog[0];
  }

  function fillSelect(element, values, selectedValue, emptyLabel, allowEmpty) {
    element.innerHTML = "";
    if (emptyLabel && (allowEmpty || !values.length)) {
      var emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = emptyLabel;
      element.appendChild(emptyOption);
    }
    values.forEach(function (value) {
      var option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      element.appendChild(option);
    });
    if (selectedValue && values.indexOf(selectedValue) === -1) {
      var savedOption = document.createElement("option");
      savedOption.value = selectedValue;
      savedOption.textContent = selectedValue;
      element.appendChild(savedOption);
    }
    element.value = selectedValue === "" ? "" : (selectedValue || (values[0] || ""));
  }

  function applyProvider(providerId, saved) {
    providerSelect.value = providerId || "zhipu";
    var provider = currentProvider();
    var isCustom = provider.id === "custom";
    providerDescription.textContent = provider.description || "";
    baseUrl.value = (saved && saved.base_url) || provider.base_url || "";
    baseUrl.readOnly = !isCustom;
    fillSelect(chatModel, provider.chat_models || [], (saved && (saved.chat_model || saved.model)) || provider.default_chat_model, "请填写聊天模型");
    var savedEmbedding = saved && Object.prototype.hasOwnProperty.call(saved, "embedding_model")
      ? saved.embedding_model
      : provider.default_embedding_model;
    fillSelect(embeddingModel, provider.embedding_models || [], savedEmbedding, "不启用向量模型（关键词检索）", true);
    chatModel.hidden = isCustom;
    embeddingModel.hidden = isCustom;
    customChatModel.hidden = !isCustom;
    customEmbeddingModel.hidden = !isCustom;
    customChatModel.value = isCustom && saved ? (saved.chat_model || saved.model || "") : "";
    customEmbeddingModel.value = isCustom && saved ? (saved.embedding_model || "") : "";
    if (isCustom) advanced.open = true;
  }

  function readStoredConfig() {
    var localSaved = {};
    var sessionSaved = {};
    try { localSaved = JSON.parse(localStorage.getItem(storageKey()) || "{}"); } catch (_error) { localSaved = {}; }
    try { sessionSaved = JSON.parse(sessionStorage.getItem(storageKey()) || "{}"); } catch (_error) { sessionSaved = {}; }
    return Object.keys(sessionSaved).length ? sessionSaved : localSaved;
  }

  function collectConfig() {
    var isCustom = providerSelect.value === "custom";
    return {
      provider_id: providerSelect.value,
      api_key: apiKey.value.trim(),
      base_url: baseUrl.value.trim(),
      chat_model: (isCustom ? customChatModel.value : chatModel.value).trim(),
      model: (isCustom ? customChatModel.value : chatModel.value).trim(),
      embedding_model: (isCustom ? customEmbeddingModel.value : embeddingModel.value).trim(),
      save_local: !!remember.checked
    };
  }

  function validateConfig(config) {
    if (!config.api_key) return "请输入 API Key。";
    if (!config.chat_model) return "请选择或填写聊天模型。";
    try { new URL(config.base_url); } catch (_error) { return "Base URL 格式无效，请填写完整的 http:// 或 https:// 地址。"; }
    return "";
  }

  async function loadCatalog() {
    try {
      var response = await fetch("/api/provider/catalog");
      if (!response.ok) throw new Error("catalog unavailable");
      var data = await response.json();
      catalog = Array.isArray(data.providers) && data.providers.length ? data.providers : fallbackCatalog;
    } catch (_error) {
      catalog = fallbackCatalog;
    }
    providerSelect.innerHTML = "";
    catalog.forEach(function (provider) {
      var option = document.createElement("option");
      option.value = provider.id;
      option.textContent = provider.name;
      providerSelect.appendChild(option);
    });
  }

  async function loadConfig() {
    await loadCatalog();
    var saved = readStoredConfig();
    applyProvider(saved.provider_id || "zhipu", saved);
    apiKey.value = saved.api_key || "";
    remember.checked = !!saved.save_local;
    if (apiKey.value) setStatus("模型配置已保存，请测试连接确认可用。", "ok", "fa-circle-check");
    else setStatus("需要配置模型后才能使用 AI 研究功能。", "warn", "fa-triangle-exclamation");
  }

  providerSelect.addEventListener("change", function () {
    applyProvider(providerSelect.value, null);
    showMessage("");
  });

  document.getElementById("apiKeyToggle").addEventListener("click", function () {
    var visible = apiKey.type === "text";
    apiKey.type = visible ? "password" : "text";
    this.setAttribute("aria-label", visible ? "显示 API Key" : "隐藏 API Key");
    this.innerHTML = visible ? '<i class="fa-regular fa-eye"></i>' : '<i class="fa-regular fa-eye-slash"></i>';
  });

  testButton.addEventListener("click", async function () {
    var config = collectConfig();
    var validationError = validateConfig(config);
    if (validationError) {
      showMessage(validationError, "error");
      return;
    }
    testButton.disabled = true;
    saveButton.disabled = true;
    setStatus("正在测试聊天和向量模型…", "", "fa-circle-notch fa-spin");
    showMessage("");
    try {
      var response = await fetch("/api/provider/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
      });
      var data = await response.json();
      if (!response.ok) throw new Error(data.detail || "连接测试失败");
      if (data.ok) {
        var capabilityText = data.capabilities && data.capabilities.embedding ? "聊天与向量模型均可用" : "聊天模型可用，向量模型未启用";
        setStatus(capabilityText + " · " + data.latency_ms + "ms", "ok", "fa-circle-check");
        showMessage(data.message || "连接测试成功。", "success");
        if (window.va && typeof window.va.track === "function") window.va.track("provider_test_succeeded");
      } else {
        setStatus("模型连接需要检查", "warn", "fa-triangle-exclamation");
        showMessage(data.message || "连接失败，请检查配置。", "error");
      }
    } catch (_error) {
      setStatus("暂时无法完成连接测试", "warn", "fa-triangle-exclamation");
      showMessage("研究服务暂时不可用，请稍后重试。", "error");
    } finally {
      testButton.disabled = false;
      saveButton.disabled = false;
    }
  });

  document.getElementById("apiForm").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!user) return;
    var config = collectConfig();
    var validationError = validateConfig(config);
    if (validationError) {
      showMessage(validationError, "error");
      return;
    }
    if (config.save_local) {
      localStorage.setItem(storageKey(), JSON.stringify(config));
      sessionStorage.removeItem(storageKey());
    } else {
      sessionStorage.setItem(storageKey(), JSON.stringify(config));
      localStorage.removeItem(storageKey());
    }
    setStatus(config.save_local ? "配置已保存在此设备。" : "配置仅在当前浏览器会话中有效。", "ok", "fa-circle-check");
    showMessage("配置已保存。现在可以返回工作台开始研究。", "success");
  });

  document.getElementById("clearApiButton").addEventListener("click", function () {
    if (!user || !window.confirm("确定清除当前浏览器中的模型配置吗？")) return;
    localStorage.removeItem(storageKey());
    sessionStorage.removeItem(storageKey());
    apiKey.value = "";
    remember.checked = false;
    applyProvider("zhipu", null);
    setStatus("模型配置已清除。", "warn", "fa-triangle-exclamation");
    showMessage("已从当前浏览器清除 API Key。", "success");
  });

  document.getElementById("signOutButton").addEventListener("click", async function () {
    this.disabled = true;
    sessionStorage.removeItem(storageKey());
    await auth.client.auth.signOut();
    window.location.replace("/auth");
  });

  if (connectGithubButton) {
    connectGithubButton.addEventListener("click", async function () {
      if (!auth || !auth.client) return;
      connectGithubButton.disabled = true;
      try {
        var options = {
          redirectTo: window.location.origin + "/app/profile#github",
          scopes: "repo read:user user:email"
        };
        var result = await auth.client.auth.signInWithOAuth({ provider: "github", options: options });
        if (result.error) throw result.error;
      } catch (_error) {
        connectGithubButton.disabled = false;
        githubConnection.className = "github-connection warn";
        githubConnection.querySelector("strong").textContent = "GitHub 授权未开始";
        githubConnection.querySelector("small").textContent = "无法打开 GitHub 授权页，请检查网络后重试。";
      }
    });
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
      refreshGithubStatus();
      loadConfig();
    });
})();
