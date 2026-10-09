// API configuration
// En dev, Vite proxya '/api' al backend (same-origin) para que la cookie HttpOnly fluya.
// El fallback es relativo; en producción se fija VITE_API_BASE_URL al backend desplegado.
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export const API_ENDPOINTS = {
  CSRF: `${API_BASE}/auth/csrf/`,
  LOGIN: `${API_BASE}/auth/login/`,
  REGISTER: `${API_BASE}/auth/register/`,
  REGISTER_EMAIL_VALIDATION: `${API_BASE}/auth/register/email-validation/`,
  PASSWORD_RESET: `${API_BASE}/auth/password-reset/`,
  PASSWORD_RESET_CONFIRM: `${API_BASE}/auth/password-reset-confirm/`,
  ME: `${API_BASE}/auth/me/`,
  DELETE_ACCOUNT: `${API_BASE}/auth/me/delete-account/`,
  LOGOUT: `${API_BASE}/auth/logout/`,
  GOOGLE_LOGIN: `${API_BASE}/auth/google/`,
  GOOGLE_COMPLETE: `${API_BASE}/auth/google/complete/`,
  PURCHASE_PROFILE: `${API_BASE}/auth/me/purchase-profile/`,
  DASHBOARD: `${API_BASE}/auth/dashboard/`,
  CONTACT: `${API_BASE}/contact/`,
  GET_USERS: `${API_BASE}/admin/users/`,
  ADMIN_ANALYSTS: `${API_BASE}/admin/analysts/`,
  GENOMICS_RESULTS: `${API_BASE}/genoma/v1/results/`,
  ANCESTRY_COHORT: `${API_BASE}/genoma/v1/results/ancestry-cohort/`,
  RECEPTION_SEARCH: `${API_BASE}/reception/search/`,
  RECEPTION_VERIFY_RUT: `${API_BASE}/reception/verify-rut/`,
  CONFIRM_PAYMENT: `${API_BASE}/services/payments/`,
};

// Session lifecycle notifications contain no user data; consumers stay lazy.
const authListeners = new Set();
let authRevision = 0;
export const subscribeAuthChanges = (listener) => {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
};
const notifyAuthChange = (change) => {
  authRevision += 1;
  authListeners.forEach((listener) => listener(change));
};
// Google endpoints that may open a session; GOOGLE_LOGIN also answers 200 without one (needs_username).
const GOOGLE_SESSION_ENDPOINTS = new Set([API_ENDPOINTS.GOOGLE_LOGIN, API_ENDPOINTS.GOOGLE_COMPLETE]);
// Reload /me after the server changed the user (e.g. purchase data submitted).
export const refreshSession = () => notifyAuthChange({ type: 'login' });

// Logout: revoca la sesión en el servidor (cookie HttpOnly) y limpia lo que se pueda sin JS.
// Se mantiene el nombre `clearToken` para no romper los llamadores existentes.
export const clearToken = async () => {
  // Invalidate immediately, even when revocation is slow or fails.
  notifyAuthChange({ type: 'logout' });
  try {
    await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
  } catch {
    /* sin sesión que revocar si el request falla */
  }
};
// El token vive en una cookie HttpOnly (ilegible por JS). No se usa localStorage.
// Helper para el patrón CSRF double-submit.
export const getCsrfToken = () => {
  if (typeof document === 'undefined') return '';

  const cookie = document.cookie
    .split(';')
    .map((entry) => entry.trim())
    .find((entry) => entry.startsWith('csrftoken='));
  if (!cookie) return '';

  const rawValue = cookie.slice('csrftoken='.length);
  try {
    return decodeURIComponent(rawValue);
  } catch {
    // Un valor de cookie malformado no debe impedir las peticiones futuras.
    return '';
  }
};

const isUnsafeMethod = (method) => !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method);

const ensureCsrfCookie = async (signal) => {
  try {
    const config = {
      method: 'GET',
      credentials: 'include',
    };
    if (signal) config.signal = signal;
    await fetch(API_ENDPOINTS.CSRF, config);
  } catch {
    // La petición principal conserva su manejo habitual de errores.
  }
  return getCsrfToken();
};

// Función helper para hacer peticiones a la API
export const apiRequest = async (endpoint, options = {}) => {
  const method = (options.method || 'GET').toUpperCase();
  const requestAuthRevision = authRevision;
  const headers = {
    ...(options.headers || {}),
  };
  // Por defecto, JSON para bodies no-File. Se omite para FormData.
  if (headers['Content-Type'] === undefined && options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  // CSRF double-submit: bootstrap y enviar X-CSRFToken en métodos mutables.
  if (isUnsafeMethod(method)) {
    let csrf = getCsrfToken();
    if (!csrf) csrf = await ensureCsrfCookie(options.signal);
    if (csrf) headers['X-CSRFToken'] = csrf;
  }
  // La autenticación viaja en cookie HttpOnly.
  const config = { ...options, headers, credentials: 'include' };

  try {
    const response = await fetch(endpoint, config);
    const contentType = response.headers.get('Content-Type') || '';
    const isJson = contentType.includes('application/json');
    const data = isJson ? await response.json() : {};

    const result = {
      ok: response.ok,
      status: response.status,
      data,
    };
    const opensSession = endpoint === API_ENDPOINTS.LOGIN
      || (GOOGLE_SESSION_ENDPOINTS.has(endpoint) && data?.success === true);
    if (opensSession && method === 'POST' && response.ok && requestAuthRevision === authRevision) {
      // A login started before logout must not reopen the shared session.
      // The next session consumer loads ME after the existing login navigation delay.
      notifyAuthChange({ type: 'login' });
    } else if (response.status === 401 && requestAuthRevision === authRevision
      && endpoint !== API_ENDPOINTS.LOGIN && endpoint !== API_ENDPOINTS.LOGOUT) {
      notifyAuthChange({ type: 'expired' });
    }
    return result;
  } catch (error) {
    console.error('API request error:', error);
    return {
      ok: false,
      status: 0,
      data: { error: 'Error de conexión con el servidor' },
    };
  }
};
