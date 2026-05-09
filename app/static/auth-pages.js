(function () {
  const mode = document.body.dataset.authMode;
  const form = document.getElementById("authForm");
  const email = document.getElementById("email");
  const password = document.getElementById("password");
  const confirmPassword = document.getElementById("confirmPassword");
  const message = document.getElementById("authMessage");

  function getNext() {
    const params = new URLSearchParams(window.location.search);
    return params.get("next") || "/";
  }

  function showMessage(text, isError = false) {
    if (!message) return;
    message.textContent = text;
    message.classList.toggle("auth-message--error", isError);
    message.classList.toggle("auth-message--ok", !isError);
  }

  async function onSubmit(event) {
    event.preventDefault();
    showMessage("");

    const emailValue = email.value.trim();
    const passwordValue = password.value;
    if (!emailValue || !passwordValue) {
      showMessage("이메일과 비밀번호를 입력하세요.", true);
      return;
    }

    try {
      if (mode === "signup") {
        if (!confirmPassword || confirmPassword.value !== passwordValue) {
          showMessage("비밀번호 확인이 일치하지 않습니다.", true);
          return;
        }
        const data = await window.Auth.signUp(emailValue, passwordValue);
        if (data?.user && !data?.session) {
          showMessage("가입되었습니다. 이메일 인증 후 로그인해 주세요.");
          return;
        }
      } else {
        await window.Auth.signIn(emailValue, passwordValue);
      }
      window.location.href = getNext();
    } catch (error) {
      showMessage(error?.message || "인증 중 오류가 발생했습니다.", true);
    }
  }

  async function init() {
    try {
      await window.Auth.getConfig();
      await window.Auth.renderAuthNav();
    } catch (error) {
      showMessage(error?.message || "인증 설정을 불러오지 못했습니다.", true);
    }

    if (!form) return;
    form.addEventListener("submit", onSubmit);
  }

  init();
})();
