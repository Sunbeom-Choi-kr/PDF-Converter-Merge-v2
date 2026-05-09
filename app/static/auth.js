(function () {
  let _configPromise;
  let _client;

  async function getConfig() {
    if (!_configPromise) {
      _configPromise = fetch("/api/auth-config")
        .then((res) => res.json())
        .catch(() => ({ enabled: false }));
    }
    return _configPromise;
  }

  async function getClient() {
    if (_client) return _client;
    const config = await getConfig();
    if (!config.enabled) {
      throw new Error("Supabase auth is not configured.");
    }
    if (!window.supabase || typeof window.supabase.createClient !== "function") {
      throw new Error("Supabase client library is missing.");
    }
    _client = window.supabase.createClient(config.supabase_url, config.supabase_anon_key, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
    return _client;
  }

  async function getSession() {
    const client = await getClient();
    const { data, error } = await client.auth.getSession();
    if (error) throw error;
    return data.session || null;
  }

  async function getAccessToken() {
    const session = await getSession();
    return session?.access_token || null;
  }

  async function getUser() {
    const session = await getSession();
    return session?.user || null;
  }

  async function getMe() {
    const token = await getAccessToken();
    if (!token) return null;
    const response = await fetch("/api/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return null;
    return response.json();
  }

  async function signIn(email, password) {
    const client = await getClient();
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }

  async function signUp(email, password) {
    const client = await getClient();
    const { data, error } = await client.auth.signUp({ email, password });
    if (error) throw error;
    return data;
  }

  async function signOut() {
    const client = await getClient();
    const { error } = await client.auth.signOut();
    if (error) throw error;
  }

  function _nextUrl() {
    return encodeURIComponent(window.location.pathname + window.location.search);
  }

  async function requireSession() {
    const session = await getSession();
    if (session) return true;
    window.location.href = `/login?next=${_nextUrl()}`;
    return false;
  }

  async function renderAuthNav() {
    const slot = document.getElementById("authNav");
    if (!slot) return;

    try {
      const user = await getUser();
      if (user) {
        const me = await getMe();
        const adminBadge = me?.is_admin ? '<span class="auth-nav__badge">[관리자]</span>' : "";
        slot.innerHTML = `
          <span class="auth-nav__email">${user.email || "로그인 사용자"} ${adminBadge}</span>
          <button id="logoutBtn" class="auth-nav__btn">로그아웃</button>
        `;
        const btn = document.getElementById("logoutBtn");
        btn?.addEventListener("click", async () => {
          await signOut();
          window.location.href = "/login";
        });
      } else {
        slot.innerHTML = `
          <a href="/login" class="auth-nav__link">로그인</a>
          <a href="/signup" class="auth-nav__link auth-nav__link--strong">회원가입</a>
        `;
      }
    } catch (e) {
      slot.innerHTML = `<span class="auth-nav__error">인증 설정 오류</span>`;
      console.error(e);
    }
  }

  window.Auth = {
    getConfig,
    getClient,
    getSession,
    getAccessToken,
    getUser,
    getMe,
    signIn,
    signUp,
    signOut,
    requireSession,
    renderAuthNav,
  };
})();
