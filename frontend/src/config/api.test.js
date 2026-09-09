import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiRequest, getCsrfToken } from './api';

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

  it('ignora cookies CSRF malformadas sin lanzar una excepción', () => {
    document.cookie = 'csrftoken=%E0%A4%A; Path=/';
    expect(getCsrfToken()).toBe('');
  });
});
