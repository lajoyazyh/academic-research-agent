(function () {
  "use strict";
  var auth = window.academicAuth;
  if (!auth || !auth.configured) return;

  var style = document.createElement("style");
  style.textContent = ".auth-gate{position:fixed;inset:0;background:rgba(15,23,42,.72);z-index:10000;display:none;align-items:center;justify-content:center;padding:20px}.auth-card{width:min(420px,100%);background:#fff;color:#172033;border-radius:16px;padding:26px;box-shadow:0 24px 70px rgba(0,0,0,.3)}.auth-card h2{margin:0 0 8px}.auth-card p{color:#64748b}.auth-card input{box-sizing:border-box;width:100%;padding:11px 12px;margin:6px 0;border:1px solid #cbd5e1;border-radius:8px}.auth-actions{display:flex;gap:10px;margin-top:14px}.auth-actions button{flex:1;padding:10px;border:0;border-radius:8px;cursor:pointer}.auth-primary{background:#2563eb;color:#fff}.auth-secondary{background:#e2e8f0}.auth-message{min-height:20px;margin-top:10px;color:#b91c1c;font-size:13px}.auth-user{position:fixed;right:16px;bottom:16px;z-index:9000;border:1px solid #cbd5e1;border-radius:999px;background:#fff;padding:8px 12px;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.12)}";
  document.head.appendChild(style);

  var gate = document.createElement("div");
  gate.className = "auth-gate";
  gate.innerHTML = '<div class="auth-card"><h2>登录学术研究助手</h2><p>登录后，你的研究会话会与其他用户隔离。模型 API Key 仍只保存在当前浏览器。</p><input id="authEmail" type="email" placeholder="邮箱" autocomplete="email"><input id="authPassword" type="password" placeholder="密码（至少 6 位）" autocomplete="current-password"><div class="auth-actions"><button class="auth-primary" id="authSignIn">登录</button><button class="auth-secondary" id="authSignUp">注册</button></div><div class="auth-message" id="authMessage"></div></div>';
  document.body.appendChild(gate);

  var userButton = document.createElement("button");
  userButton.className = "auth-user";
  userButton.textContent = "退出登录";
  userButton.style.display = "none";
  userButton.onclick = function () { auth.client.auth.signOut(); };
  document.body.appendChild(userButton);

  function showMessage(message) { document.getElementById("authMessage").textContent = message || ""; }
  function requireLogin() { gate.style.display = "flex"; userButton.style.display = "none"; }
  window.academicAuthRequireLogin = requireLogin;

  async function submit(mode) {
    showMessage("");
    var email = document.getElementById("authEmail").value.trim();
    var password = document.getElementById("authPassword").value;
    if (!email || password.length < 6) { showMessage("请输入有效邮箱和至少 6 位密码。"); return; }
    var result = mode === "signup"
      ? await auth.client.auth.signUp({ email: email, password: password })
      : await auth.client.auth.signInWithPassword({ email: email, password: password });
    if (result.error) showMessage(result.error.message);
    else if (mode === "signup" && !result.data.session) showMessage("注册成功，请检查邮箱并完成验证。");
  }
  document.getElementById("authSignIn").onclick = function () { submit("signin"); };
  document.getElementById("authSignUp").onclick = function () { submit("signup"); };

  auth.client.auth.onAuthStateChange(function (_event, session) {
    window.academicAuthUserId = session && session.user ? session.user.id : "anonymous";
    window.dispatchEvent(new CustomEvent("academic-auth-changed", { detail: { userId: window.academicAuthUserId } }));
    gate.style.display = session ? "none" : "flex";
    userButton.style.display = session ? "block" : "none";
  });
  auth.client.auth.getSession().then(function (result) {
    if (!result.data.session) requireLogin();
    else userButton.style.display = "block";
  });
})();
