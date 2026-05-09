(function () {
  const page = document.body?.dataset?.page;
  const messageEl = document.getElementById("paymentMessage");

  function setMessage(text, isError) {
    if (!messageEl) return;
    messageEl.textContent = text;
    messageEl.classList.remove("auth-message--error", "auth-message--ok");
    messageEl.classList.add(isError ? "auth-message--error" : "auth-message--ok");
  }

  function makeOrderId() {
    const stamp = Date.now().toString(36);
    const rand = Math.random().toString(36).slice(2, 10);
    return `pro_${stamp}_${rand}`;
  }

  async function initCheckoutPage() {
    await window.Auth.renderAuthNav();
    const token = await window.Auth.getAccessToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const me = await window.Auth.getMe();
    if (!me?.is_admin) {
      setMessage("관리자 계정만 결제 페이지에 접근할 수 있습니다.", true);
      return;
    }

    const configResp = await fetch("/api/toss-config");
    const config = await configResp.json();
    if (!config.enabled || !config.client_key) {
      setMessage("Toss 결제 키가 설정되지 않았습니다. 서버 환경변수를 먼저 설정하세요.", true);
      return;
    }

    const button = document.getElementById("tossPayButton");
    if (!button) return;

    async function requestTossPayment() {
      try {
        const tossPayments = TossPayments(config.client_key);
        const orderId = makeOrderId();
        await tossPayments.requestPayment("CARD", {
          amount: {
            currency: "KRW",
            value: 9900,
          },
          orderId: orderId,
          orderName: "PDF Converter Pro 월 구독",
          successUrl: window.location.origin + "/payment/success",
          failUrl: window.location.origin + "/payment/fail",
          customerEmail: me.email || undefined,
        });
      } catch (error) {
        setMessage(`결제창 호출 실패: ${error?.message || "알 수 없는 오류"}`, true);
        button.classList.remove("hidden");
      }
    }

    // Auto-open payment module immediately after entering /payment
    // from the "결제하기 (관리자)" click path.
    await requestTossPayment();

    // Manual retry fallback (for popup blocker / browser restrictions).
    button.addEventListener("click", requestTossPayment);
  }

  async function initSuccessPage() {
    const token = await window.Auth.getAccessToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const me = await window.Auth.getMe();
    if (!me?.is_admin) {
      setMessage("관리자 계정이 아니어서 결제를 승인할 수 없습니다.", true);
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const paymentKey = params.get("paymentKey");
    const orderId = params.get("orderId");
    const amount = params.get("amount");
    if (!paymentKey || !orderId || !amount) {
      setMessage("결제 승인에 필요한 쿼리 파라미터가 누락되었습니다.", true);
      return;
    }

    const resp = await fetch("/api/toss/confirm", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        paymentKey: paymentKey,
        orderId: orderId,
        amount: Number(amount),
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const detail = data?.detail?.message || data?.detail || "결제 승인에 실패했습니다.";
      setMessage(`결제 승인 실패: ${detail}`, true);
      return;
    }

    setMessage(`결제 승인 완료: ${data.orderName || "주문"} / ${data.totalAmount || amount}원`, false);
  }

  function initFailPage() {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code") || "UNKNOWN";
    const msg = params.get("message") || "결제 실패";
    setMessage(`실패 코드: ${code} / 메시지: ${msg}`, true);
  }

  if (page === "payment") {
    initCheckoutPage();
  } else if (page === "payment-success") {
    initSuccessPage();
  } else if (page === "payment-fail") {
    initFailPage();
  }
})();
