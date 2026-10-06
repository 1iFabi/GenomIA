import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken, getCsrfToken, subscribeAuthChanges } from './api';

const retiredSnpEndpoints = [
  'DISEASES', 'ANCESTRY', 'INDIGENOUS', 'TRAITS', 'PHARMACOGENETICS',
  'UPLOAD_GENETIC_FILE', 'DELETE_GENETIC_FILE',
];

describe('legacy SNP API retirement', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it.each(['', 'https://api.example.test/api'])(
    'does not expose legacy result or genetic-file URLs with base "%s"',
    async (base) => {
      vi.stubEnv('VITE_API_BASE_URL', base);
      vi.resetModules();
      const { API_ENDPOINTS } = await import('./api');

      for (const endpoint of retiredSnpEndpoints) {
        expect(API_ENDPOINTS).not.toHaveProperty(endpoint);
      }
      expect(Object.values(API_ENDPOINTS).some((value) => (
        typeof value === 'string' && /\/(genetics\/(diseases|ancestry|indigenous|traits|pharmacogenetics)|ingest\/(upload|delete)-genetic-file)\//.test(value)
      ))).toBe(false);
    },
  );
});

describe('apiRequest (auth via cookie HttpOnly)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    document.cookie = 'csrftoken=abc123; Path=/';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'csrftoken=; Path=/';
  });

  const mockJson = (body = { ok: true }) =>
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });

  it('envía credentials:include (el token viaja en cookie HttpOnly)', async () => {
    globalThis.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/', { method: 'GET' });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/auth/me/',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('no inyecta Authorization manual (la cookie viaja sola)', async () => {
    globalThis.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/', { method: 'GET' });
    const [, opts] = globalThis.fetch.mock.calls[0];
    expect(opts.headers['Authorization']).toBeUndefined();
  });

  it('añade X-CSRFToken en métodos mutables (double-submit)', async () => {
    globalThis.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/change-password/', { method: 'POST', body: '{}' });
    const [, opts] = globalThis.fetch.mock.calls[0];
    expect(opts.headers['X-CSRFToken']).toBe('abc123');
  });

  it('no añade X-CSRFToken en GET', async () => {
    globalThis.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/', { method: 'GET' });
    const [, opts] = globalThis.fetch.mock.calls[0];
    expect(opts.headers['X-CSRFToken']).toBeUndefined();
  });

  it('obtiene la cookie CSRF antes de un método mutable si falta', async () => {
    document.cookie = 'csrftoken=; Max-Age=0; Path=/';
    globalThis.fetch.mockResolvedValue(mockJson());

    await apiRequest('/api/auth/logout/', { method: 'POST' });

    expect(globalThis.fetch).toHaveBeenNthCalledWith(
      1,
      '/api/auth/csrf/',
      { method: 'GET', credentials: 'include' },
    );
    expect(globalThis.fetch).toHaveBeenNthCalledWith(
      2,
      '/api/auth/logout/',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('clearToken invalidates auth immediately and awaits exactly one authenticated logout POST', async () => {
    let finishLogout;
    globalThis.fetch.mockImplementationOnce(() => new Promise((resolve) => { finishLogout = resolve; }));
    const listener = vi.fn();
    const unsubscribe = subscribeAuthChanges(listener);
    try {
      let settled = false;
      const logout = clearToken().then(() => { settled = true; });
      expect(listener).toHaveBeenCalledExactlyOnceWith({ type: 'logout' });
      expect(globalThis.fetch).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.LOGOUT, {
        method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': 'abc123' },
      });
      await Promise.resolve();
      expect(settled).toBe(false);
      finishLogout(mockJson());
      await logout;
      expect(settled).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      unsubscribe();
    }
  });

  it.each(['HTTP failure', 'network rejection'])(
    'clearToken still completes and invalidates auth once after %s without retrying', async (failure) => {
      if (failure === 'network rejection') {
        globalThis.fetch.mockRejectedValueOnce(new Error('Logout unavailable'));
      } else {
        globalThis.fetch.mockResolvedValueOnce(new Response('{}', {
          status: 503, headers: { 'Content-Type': 'application/json' },
        }));
      }
      const listener = vi.fn();
      const unsubscribe = subscribeAuthChanges(listener);
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      try {
        await expect(clearToken()).resolves.toBeUndefined();
        expect(listener).toHaveBeenCalledExactlyOnceWith({ type: 'logout' });
        expect(globalThis.fetch).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.LOGOUT, {
          method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': 'abc123' },
        });
      } finally {
        unsubscribe();
        errorSpy.mockRestore();
      }
    }
  );

  it('ignora cookies CSRF malformadas sin lanzar una excepción', () => {
    document.cookie = 'csrftoken=%E0%A4%A; Path=/';
    expect(getCsrfToken()).toBe('');
  });
});
