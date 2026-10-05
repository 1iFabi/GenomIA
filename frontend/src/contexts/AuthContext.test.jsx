import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../config/api';
import { useSession } from '../hooks/useSession';
import { AuthProvider } from './AuthContext';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ProtectedRoute from '../components/ProtectedRoute';
import Profile from '../pages/Profile/Profile';
import Pending from '../pages/Pending/Pending';
import NoPurchased from '../pages/NoPurchased/NoPurchased';

vi.mock('../components/Wait', () => ({ default: () => null }));
vi.mock('../components/ChangePasswordModal/ChangePasswordModal', () => ({ default: () => null }));
vi.mock('../components/DeleteAccountModal/DeleteAccountModal', () => ({ default: () => null }));

let container;
let root;
const reply = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
});
const Probe = () => {
  const { user, loading, isLoggedIn } = useSession();
  return <output>{JSON.stringify({ user, loading, isLoggedIn })}</output>;
};
const render = async (children) => act(async () => root.render(
  <React.StrictMode><AuthProvider>{children}</AuthProvider></React.StrictMode>
));
const current = () => JSON.parse(container.querySelector('output').textContent);
const meCalls = () => fetch.mock.calls.filter(([url]) => url === API_ENDPOINTS.ME);

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('fetch', vi.fn(async () => reply({ user: { name: 'Ada', roles: ['ANALISTA'] } })));
  document.cookie = 'csrftoken=abc123; Path=/';
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  document.cookie = 'csrftoken=; Max-Age=0; Path=/';
  vi.unstubAllGlobals();
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
});

describe('shared current user', () => {
  it('does not request ME merely because the provider wraps a public view', async () => {
    await render(<div>Public</div>);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(['wrapped', 'direct'])('shares the %s user across concurrent consumers and remounts', async (shape) => {
    const user = { name: 'Ada', roles: ['ANALISTA'], service_status: 'PENDING' };
    fetch.mockImplementation(async () => reply(shape === 'wrapped' ? { user } : user));
    await render(<><Probe /><Probe /></>);
    expect([...container.querySelectorAll('output')].map((node) => JSON.parse(node.textContent).user))
      .toEqual([user, user]);
    await render(<div>Between protected pages</div>);
    await render(<Probe />);
    expect(current()).toEqual({ user, loading: false, isLoggedIn: true });
    expect(meCalls()).toHaveLength(1);
  });

  it.each([
    ['/profile', 'COMPLETED', <Profile />],
    ['/pending', 'PENDING', <Pending />],
    ['/no-purchased', 'NO_PURCHASED', <NoPurchased />],
  ])('shares the guard profile with the account view at %s', async (path, serviceStatus, page) => {
    fetch.mockImplementation(async () => reply({ user: { first_name: 'Ada', service_status: serviceStatus } }));
    await render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={path} element={<ProtectedRoute requireService={false}>{page}</ProtectedRoute>} />
        </Routes>
      </MemoryRouter>
    );
    expect(container.textContent).toContain('Ada');
    expect(meCalls()).toHaveLength(1);
  });

  it.each([200, 401])('discards a pending ME result (%s) after logout without reloading the old cookie', async (status) => {
    let resolveMe;
    fetch.mockImplementation((url) => url === API_ENDPOINTS.ME
      ? new Promise((resolve) => { resolveMe = resolve; }) : Promise.resolve(reply({})));
    await render(<Probe />);
    expect(current().loading).toBe(true);
    await act(async () => { await clearToken(); });
    await act(async () => resolveMe(reply(status === 200 ? { user: { name: 'Stale' } } : {}, status)));
    await render(<Probe key="new-protected-page" />);
    expect(current()).toEqual({ user: null, loading: false, isLoggedIn: false });
    expect(meCalls()).toHaveLength(1);
  });

  it('clears an authenticated user even when server logout fails', async () => {
    await render(<Probe />);
    fetch.mockImplementation(async () => reply({ error: 'Unavailable' }, 500));
    await act(async () => { await clearToken(); });
    expect(current()).toEqual({ user: null, loading: false, isLoggedIn: false });
  });

  it('ignores a successful login started before logout and keeps later consumers signed out', async () => {
    await render(<Probe />);
    expect(current().isLoggedIn).toBe(true);
    let resolveLogin;
    fetch.mockImplementation((url) => url === API_ENDPOINTS.LOGIN
      ? new Promise((resolve) => { resolveLogin = resolve; })
      : Promise.resolve(reply({ user: { name: 'Stale' } })));
    const loginRequest = apiRequest(API_ENDPOINTS.LOGIN, { method: 'POST', body: '{}' });
    expect(resolveLogin).toBeTypeOf('function');

    await act(async () => { await clearToken(); });
    expect(current()).toEqual({ user: null, loading: false, isLoggedIn: false });
    await act(async () => {
      resolveLogin(reply({}));
      expect((await loginRequest).ok).toBe(true);
    });
    await render(<Probe key="after-stale-login" />);
    expect(current()).toEqual({ user: null, loading: false, isLoggedIn: false });
    expect(meCalls()).toHaveLength(1);
  });

  it('invalidates on successful login started after logout but waits for a later consumer mount to load the new user', async () => {
    await render(<Probe />);
    await act(async () => { await clearToken(); });
    fetch.mockImplementation(async (url) => reply(url === API_ENDPOINTS.ME
      ? { user: { name: 'Grace', service_status: 'COMPLETED' } } : {}));
    await act(async () => { await apiRequest(API_ENDPOINTS.LOGIN, { method: 'POST', body: '{}' }); });
    expect(current().user).toBeNull();
    expect(meCalls()).toHaveLength(1);
    await render(<Probe key="after-login" />);
    expect(current().user.name).toBe('Grace');
    expect(meCalls()).toHaveLength(2);
  });

  it('does not retain authentication after an API reports an expired session', async () => {
    await render(<Probe />);
    fetch.mockImplementation(async () => reply({ error: 'Unauthenticated' }, 401));
    await act(async () => { await apiRequest('/protected-resource'); });
    expect(current()).toEqual({ user: null, loading: false, isLoggedIn: false });
  });

  it('ignores a pre-login request that reports 401 after the new session was loaded', async () => {
    await render(<Probe />);
    let resolveOld;
    fetch.mockImplementation((url) => url === '/old-resource'
      ? new Promise((resolve) => { resolveOld = resolve; }) : Promise.resolve(reply({ user: { name: 'Grace' } })));
    const oldRequest = apiRequest('/old-resource');
    await act(async () => { await apiRequest(API_ENDPOINTS.LOGIN, { method: 'POST', body: '{}' }); });
    await render(<Probe key="new-session" />);
    await act(async () => { resolveOld(reply({}, 401)); await oldRequest; });
    expect(current().user.name).toBe('Grace');
  });

  it('preserves authenticated state for a resource permission denial or failed login', async () => {
    await render(<Probe />);
    fetch.mockImplementation(async (url) => reply({}, url === API_ENDPOINTS.LOGIN ? 401 : 403));
    await act(async () => {
      expect((await apiRequest('/forbidden-resource')).status).toBe(403);
      expect((await apiRequest(API_ENDPOINTS.LOGIN, { method: 'POST', body: '{}' })).status).toBe(401);
    });
    expect(current().user.name).toBe('Ada');
    expect(meCalls()).toHaveLength(1);
  });

  it.each([401, 500])('allows a new consumer to retry a failed ME response (%s)', async (status) => {
    fetch.mockImplementationOnce(async () => reply({ error: 'Unavailable' }, status));
    await render(<Probe />);
    expect(current()).toEqual({ user: null, loading: false, isLoggedIn: false });
    await render(<Probe key="retry" />);
    expect(current().user.name).toBe('Ada');
    expect(meCalls()).toHaveLength(2);
  });
});
