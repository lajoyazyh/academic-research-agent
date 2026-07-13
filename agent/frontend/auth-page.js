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

  function destination() {
    var next = new URLSearchParams(window.location.search).get("next") || "/";
    return next.charAt(0) === "/" && next.slice(0, 2) !== "//" ? next : "/";
  }

  function showMessage(text, type) {
    message.textContent = text || "";
    message.className = "form-message" + (text ? " visible " + (type || "error") : "");
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
    title.textContent = isSignup ? "创建账号" : "欢迎回来";
    description.textContent = isSignup ? "注册后即可创建你的独立研究工作区。" : "登录后继续你的研究工作。";
    submitButton.textContent = isSignup ? "注册" : "登录";
    showMessage("");
  }

  if (!auth || !auth.configured || !auth.client) {
    submitButton.disabled = true;
    showMessage("登录服务尚未配置，请联系站点管理员。", "error");
    return;
  }

  signInTab.addEventListener("click", function () { setMode("signin"); });
  signUpTab.addEventListener("click", function () { setMode("signup"); });
  document.getElementById("passwordToggle").addEventListener("click", function () {
    var visible = password.type === "text";
    password.type = visible ? "password" : "text";
    this.setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
    this.innerHTML = visible ? '<i class="fa-regular fa-eye"></i>' : '<i class="fa-regular fa-eye-slash"></i>';
  });

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
        window.location.replace(destination());
      } else {
        showMessage("注册成功。请打开验证邮件完成确认，然后返回登录。", "success");
      }
    } catch (error) {
      showMessage(error && error.message ? error.message : "操作失败，请稍后重试。", "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = mode === "signup" ? "注册" : "登录";
    }
  });

  auth.client.auth.getSession().then(function (result) {
    if (result.data && result.data.session) window.location.replace(destination());
  });
})();
