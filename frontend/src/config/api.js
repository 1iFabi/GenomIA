// API configuration
// En dev, Vite proxya '/api' al backend (same-origin) para que la cookie HttpOnly fluya.
// El fallback es relativo; en producción se fija VITE_API_BASE_URL al backend desplegado.
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export const API_ENDPOINTS = {
  // Origen (sin /api) para construir URLs absolutas en llamadas puntuales.
  BASE_URL: API_BASE.replace(/\/api\/?$/, ''),
  CSRF: `${API_BASE}/auth/csrf/`,
  LOGIN: `${API_BASE}/auth/login/`,
  REGISTER: `${API_BASE}/auth/register/`,
  REGISTER_EMAIL_VALIDATION: `${API_BASE}/auth/register/email-validation/`,
  PASSWORD_RESET: `${API_BASE}/auth/password-reset/`,
  PASSWORD_RESET_CONFIRM: `${API_BASE}/auth/password-reset-confirm/`,
  ME: `${API_BASE}/auth/me/`,
  DELETE_ACCOUNT: `${API_BASE}/auth/me/delete-account/`,
  LOGOUT: `${API_BASE}/auth/logout/`,
  DASHBOARD: `${API_BASE}/auth/dashboard/`,
  CONTACT: `${API_BASE}/contact/`,
  GET_USERS: `${API_BASE}/admin/users/`,
  ADMIN_ANALYSTS: `${API_BASE}/admin/analysts/`,
  UPLOAD_GENETIC_FILE: `${API_BASE}/ingest/upload-genetic-file/`,
  DELETE_GENETIC_FILE: `${API_BASE}/ingest/delete-genetic-file/`,
  UPDATE_SERVICE_STATUS: `${API_BASE}/auth/service/status/`,
  DISEASES: `${API_BASE}/genetics/diseases/`,
  PATIENT_VARIANTS: (userId) => `${API_BASE}/genetics/patient-variants/${userId}/`,
  VARIANTS: `${API_BASE}/genetics/variantes/`,
  ANCESTRY: `${API_BASE}/genetics/ancestry/`,
  INDIGENOUS: `${API_BASE}/genetics/indigenous/`,
  TRAITS: `${API_BASE}/genetics/traits/`,
  BIOMETRICS: `${API_BASE}/genetics/biometrics/`,
  BIOMARKERS: `${API_BASE}/genetics/biomarkers/`,
  PHARMACOGENETICS: `${API_BASE}/genetics/pharmacogenetics/`,
  RECEPTION_SEARCH: `${API_BASE}/reception/search/`,
  RECEPTION_MARK_ARRIVAL: `${API_BASE}/reception/arrival/`,
  RECEPTION_SAMPLE_CODE: `${API_BASE}/reception/sample-code/`,
  RECEPTION_SAMPLE_STATUS: `${API_BASE}/reception/sample-status/`,
};

// Logout: revoca la sesión en el servidor (cookie HttpOnly) y limpia lo que se pueda sin JS.
// Se mantiene el nombre `clearToken` para no romper los llamadores existentes.
export const clearToken = async () => {
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

    return {
      ok: response.ok,
      status: response.status,
      data,
    };
  } catch (error) {
    console.error('API request error:', error);
    return {
      ok: false,
      status: 0,
      data: { error: 'Error de conexión con el servidor' },
    };
  }
};
