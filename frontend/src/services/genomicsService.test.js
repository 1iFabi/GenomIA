import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const serviceEndpointCases = [
  ['results', 'GENOMICS_SERVICE_RESULTS'],
  ['metrics', 'GENOMICS_SERVICE_METRICS'],
];
const encodedServiceId = 'request%2Fa%20b%3F%23%25%2B%C3%A1';
const serviceId = 'request/a b?#%+á';
const readCases = [
  ['getGenomicsServices', [], '/api/genoma/v1/services/'],
  ['getGenomicsServiceResults', ['service-123'], '/api/genoma/v1/services/service-123/results/'],
];
let api;

const mockJson = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

beforeEach(async () => {
  vi.resetModules();
  vi.stubEnv('VITE_API_BASE_URL', '');
  vi.stubGlobal('fetch', vi.fn());
  document.cookie = 'csrftoken=abc123; Path=/';
  api = await import('../config/api');
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  document.cookie = 'csrftoken=; Max-Age=0; Path=/';
});

describe('owner-scoped genoma v1 URLs', () => {
  it('exposes the default service list URL', () => {
    expect(api.API_ENDPOINTS.GENOMICS_SERVICES).toBe('/api/genoma/v1/services/');
  });

  it.each(serviceEndpointCases)('builds the default service %s URL', (resource, endpoint) => {
    expect(api.API_ENDPOINTS[endpoint]('service-123')).toBe(
      `/api/genoma/v1/services/service-123/${resource}/`,
    );
  });

  it.each(serviceEndpointCases)('encodes the service ID in the %s path', (resource, endpoint) => {
    expect(api.API_ENDPOINTS[endpoint](serviceId)).toBe(
      `/api/genoma/v1/services/${encodedServiceId}/${resource}/`,
    );
  });

  it('uses the configured API base for all genoma v1 endpoints', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test/api');
    vi.resetModules();
    const { API_ENDPOINTS } = await import('../config/api');

    expect(API_ENDPOINTS.GENOMICS_SERVICES).toBe('https://api.example.test/api/genoma/v1/services/');
    expect(API_ENDPOINTS.GENOMICS_SERVICE_RESULTS('service-123')).toBe(
      'https://api.example.test/api/genoma/v1/services/service-123/results/',
    );
    expect(API_ENDPOINTS.GENOMICS_SERVICE_METRICS('service-123')).toBe(
      'https://api.example.test/api/genoma/v1/services/service-123/metrics/',
    );
  });

  it('preserves account, user, service-status and reception endpoints', () => {
    expect(api.API_ENDPOINTS).toMatchObject({
      CSRF: '/api/auth/csrf/',
      LOGIN: '/api/auth/login/',
      REGISTER: '/api/auth/register/',
      REGISTER_EMAIL_VALIDATION: '/api/auth/register/email-validation/',
      PASSWORD_RESET: '/api/auth/password-reset/',
      PASSWORD_RESET_CONFIRM: '/api/auth/password-reset-confirm/',
      ME: '/api/auth/me/',
      DELETE_ACCOUNT: '/api/auth/me/delete-account/',
      LOGOUT: '/api/auth/logout/',
      DASHBOARD: '/api/auth/dashboard/',
      CONTACT: '/api/contact/',
      GET_USERS: '/api/admin/users/',
      ADMIN_ANALYSTS: '/api/admin/analysts/',
      RECEPTION_SEARCH: '/api/reception/search/',
      RECEPTION_VERIFY_RUT: '/api/reception/verify-rut/',
      CONFIRM_PAYMENT: '/api/services/payments/',
    });
  });

  it.each(['', 'https://api.example.test/api'])(
    'does not advertise the retired SNP catalog with API base "%s"',
    async (base) => {
      vi.stubEnv('VITE_API_BASE_URL', base);
      vi.resetModules();
      const { API_ENDPOINTS } = await import('../config/api');

      expect(API_ENDPOINTS).not.toHaveProperty('VARIANTS');
      expect(Object.values(API_ENDPOINTS).some((value) => (
        typeof value === 'string' && value.includes('/genetics/variantes/')
      ))).toBe(false);
    },
  );

  it.each(['', 'https://api.example.test/api'])(
    'does not advertise retired biomarker or biometrics APIs with base "%s"',
    async (base) => {
      vi.stubEnv('VITE_API_BASE_URL', base);
      vi.resetModules();
      const { API_ENDPOINTS } = await import('../config/api');

      expect(API_ENDPOINTS).not.toHaveProperty('BIOMARKERS');
      expect(API_ENDPOINTS).not.toHaveProperty('BIOMETRICS');
      expect(Object.values(API_ENDPOINTS).some((value) => (
        typeof value === 'string' && /\/genetics\/(biomarkers|biometrics)\//.test(value)
      ))).toBe(false);
    },
  );

  it.each(['', 'https://api.example.test/api'])(
    'does not advertise the retired patient-variant reader with API base "%s"',
    async (base) => {
      vi.stubEnv('VITE_API_BASE_URL', base);
      vi.resetModules();
      const { API_ENDPOINTS } = await import('../config/api');

      expect(API_ENDPOINTS).not.toHaveProperty('PATIENT_VARIANTS');
    },
  );
});

describe('genomics GET helpers', () => {
  let genomicsService;

  beforeEach(async () => {
    genomicsService = await import('./genomicsService');
  });

  it.each(readCases)('%s uses cookie-authenticated GET and preserves the response envelope', async (helper, args, url) => {
    const data = { data: { items: [] }, metadata: { schema_version: 1 } };
    globalThis.fetch.mockResolvedValue(mockJson(data));

    const response = await genomicsService[helper](...args);

    expect(response).toEqual({ ok: true, status: 200, data });
    expect(globalThis.fetch).toHaveBeenCalledExactlyOnceWith(url, {
      method: 'GET',
      credentials: 'include',
      headers: {},
    });
    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('Authorization');
    expect(options.headers).not.toHaveProperty('X-CSRFToken');
  });

  it.each(readCases)('%s preserves unsuccessful response status and data', async (helper, args) => {
    const data = { error: 'Service request not found' };
    globalThis.fetch.mockResolvedValue(mockJson(data, 404));

    expect(await genomicsService[helper](...args)).toEqual({ ok: false, status: 404, data });
  });

  it.each(readCases)('%s delegates to apiRequest without changing its envelope', async (helper, args, url) => {
    const envelope = { ok: true, status: 200, data: { items: [] } };
    const request = vi.spyOn(api, 'apiRequest').mockResolvedValue(envelope);

    expect(await genomicsService[helper](...args)).toBe(envelope);
    expect(request).toHaveBeenCalledExactlyOnceWith(url, { method: 'GET' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it.each([
    ['getGenomicsServiceResults', 'results'],
  ])('%s requests an encoded service ID', async (helper, resource) => {
    globalThis.fetch.mockResolvedValue(mockJson({ items: [] }));

    await genomicsService[helper](serviceId);

    expect(globalThis.fetch).toHaveBeenCalledExactlyOnceWith(
      `/api/genoma/v1/services/${encodedServiceId}/${resource}/`,
      { method: 'GET', credentials: 'include', headers: {} },
    );
  });
});
