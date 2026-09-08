import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiRequest } from './api';

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
    global.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/', { method: 'GET' });
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/auth/me/',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('no inyecta Authorization manual (la cookie viaja sola)', async () => {
    global.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/', { method: 'GET' });
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['Authorization']).toBeUndefined();
  });

  it('añade X-CSRFToken en métodos mutables (double-submit)', async () => {
    global.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/change-password/', { method: 'POST', body: '{}' });
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['X-CSRFToken']).toBe('abc123');
  });

  it('no añade X-CSRFToken en GET', async () => {
    global.fetch.mockResolvedValue(mockJson());
    await apiRequest('/api/auth/me/', { method: 'GET' });
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['X-CSRFToken']).toBeUndefined();
  });
});
