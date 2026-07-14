(function () {
  "use strict";

  var auth = window.academicAuth;
  var mode = "signin";
  var form = document.getElementById("authForm");
  var signInTab = document.getElementById("signInTab");
  var signUpTab = document.getElementById("signUpTab");
  var title = document.getElementById("authTitle");
  var description = document.getElementById("authDescription");
  var displayNameField = document.getElementById("displayNameField");
  var passwordHelp = document.getElementById("passwordHelp");
  var submitButton = document.getElementById("authSubmit");
  var message = document.getElementById("authMessage");
  var password = document.getElementById("authPassword");
  var forgotPassword = document.getElementById("forgotPassword");
  var githubAuthButton = document.getElementById("githubAuthButton");

  function destination() {
    var next = new URLSearchParams(window.location.search).get("next") || "/app";
    return next.charAt(0) === "/" && next.slice(0, 2) !== "//" ? next : "/app";
  }

  function showMessage(text, type) {
    message.textContent = text || "";
    message.className = "form-message" + (text ? " visible " + (type || "error") : "");
  }

  function friendlyAuthError(error) {
    var messageText = String(error && error.message || "").toLowerCase();
    if (messageText.indexOf("invalid login credentials") >= 0) return "邮箱或密码不正确，请重新输入。";
    if (messageText.indexOf("email not confirmed") >= 0) return "邮箱尚未验证，请先打开验证邮件。";
    if (messageText.indexOf("user already registered") >= 0) return "这个邮箱已经注册，请直接登录。";
    if (messageText.indexOf("password") >= 0 && messageText.indexOf("weak") >= 0) return "密码强度不足，请使用更长的密码。";
    if (messageText.indexOf("rate") >= 0 || messageText.indexOf("too many") >= 0) return "尝试次数过多，请稍后再试。";
    if (messageText.indexOf("network") >= 0 || messageText.indexOf("fetch") >= 0) return "网络连接失败，请检查网络后重试。";
    return "操作没有完成，请稍后重试。";
  }

  function setMode(nextMode) {
    mode = nextMode;
    var isSignup = mode === "signup";
    signInTab.classList.toggle("active", !isSignup);
    signUpTab.classList.toggle("active", isSignup);
    signInTab.setAttribute("aria-selected", String(!isSignup));
    signUpTab.setAttribute("aria-selected", String(isSignup));
    displayNameField.hidden = !isSignup;
    passwordHelp.hidden = !isSignup;
    password.autocomplete = isSignup ? "new-password" : "current-password";
    if (forgotPassword) forgotPassword.hidden = isSignup;
    title.textContent = isSignup ? "创建账号" : "欢迎回来";
    description.textContent = isSignup ? "注册后即可创建你的独立研究工作区。" : "登录后继续你的研究工作。";
    submitButton.textContent = isSignup ? "注册" : "登录";
    showMessage("");
  }

  if (!auth || !auth.configured || !auth.client) {
    submitButton.disabled = true;
    if (githubAuthButton) githubAuthButton.disabled = true;
    showMessage("登录服务尚未配置，请联系站点管理员。", "error");
    return;
  }

  signInTab.addEventListener("click", function () { setMode("signin"); });
  signUpTab.addEventListener("click", function () { setMode("signup"); });
  if (new URLSearchParams(window.location.search).get("mode") === "signup") setMode("signup");
  if (githubAuthButton) {
    githubAuthButton.addEventListener("click", async function () {
      githubAuthButton.disabled = true;
      showMessage("正在前往 GitHub 授权…", "success");
      try {
        var result = await auth.client.auth.signInWithOAuth({
          provider: "github",
          options: {
            redirectTo: window.location.origin + destination(),
            scopes: "repo read:user user:email"
          }
        });
        if (result.error) throw result.error;
      } catch (error) {
        githubAuthButton.disabled = false;
        showMessage(friendlyAuthError(error), "error");
      }
    });
  }
  document.getElementById("passwordToggle").addEventListener("click", function () {
    var visible = password.type === "text";
    password.type = visible ? "password" : "text";
    this.setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
    this.innerHTML = visible ? '<i class="fa-regular fa-eye"></i>' : '<i class="fa-regular fa-eye-slash"></i>';
  });

  if (forgotPassword) {
    forgotPassword.addEventListener("click", async function () {
      var email = document.getElementById("authEmail").value.trim();
      if (!email) {
        showMessage("请先输入需要重置密码的邮箱。", "error");
        document.getElementById("authEmail").focus();
        return;
      }
      forgotPassword.disabled = true;
      showMessage("正在发送重置邮件…", "success");
      try {
        var result = await auth.client.auth.resetPasswordForEmail(email, {
          redirectTo: window.location.origin + "/auth?next=" + encodeURIComponent(destination())
        });
        if (result.error) throw result.error;
        showMessage("重置邮件已发送，请检查收件箱和垃圾邮件。", "success");
      } catch (error) {
        showMessage(error && error.message ? error.message : "暂时无法发送重置邮件，请稍后重试。", "error");
      } finally {
        forgotPassword.disabled = false;
      }
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    showMessage("");
    var email = document.getElementById("authEmail").value.trim();
    var passwordValue = password.value;
    if (!email || passwordValue.length < 6) {
      showMessage("请输入有效邮箱和至少 6 位密码。", "error");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = mode === "signup" ? "正在注册…" : "正在登录…";
    try {
      var result;
      if (mode === "signup") {
        var displayName = document.getElementById("displayName").value.trim();
        result = await auth.client.auth.signUp({
          email: email,
          password: passwordValue,
          options: {
            emailRedirectTo: window.location.origin + "/auth?next=" + encodeURIComponent(destination()),
            data: { display_name: displayName }
          }
        });
      } else {
        result = await auth.client.auth.signInWithPassword({ email: email, password: passwordValue });
      }
      if (result.error) throw result.error;
      if (result.data && result.data.session) {
        if (mode === "signup" && window.va && typeof window.va.track === "function") window.va.track("signup_completed");
        window.location.replace(destination());
      } else {
        if (mode === "signup" && window.va && typeof window.va.track === "function") window.va.track("signup_completed");
        showMessage("注册成功。请打开验证邮件完成确认，然后返回登录。", "success");
      }
    } catch (error) {
      showMessage(friendlyAuthError(error), "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = mode === "signup" ? "注册" : "登录";
    }
  });

  auth.client.auth.getSession().then(function (result) {
    if (result.data && result.data.session) window.location.replace(destination());
  });
})();
