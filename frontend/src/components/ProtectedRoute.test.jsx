import React, { act, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { apiRequest, clearToken } from '../config/api';
import { AuthProvider } from '../contexts/AuthContext';
import { useSession } from '../hooks/useSession';
import ProtectedRoute from './ProtectedRoute';

vi.mock('../config/api', async (importOriginal) => ({
  ...await importOriginal(),
  API_ENDPOINTS: { ME: '/me' },
  apiRequest: vi.fn(),
}));

let container;
let root;

const renderRoute = async (path, element) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <React.StrictMode>
        <AuthProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path={`${path.split('/').slice(0, 2).join('/')}/*`} element={element} />
              {['/login', '/dashboard', '/no-purchased', '/pending']
                .filter((destination) => destination !== path.split('/').slice(0, 2).join('/'))
                .map((destination) => (
                  <Route key={destination} path={destination} element={<output>{destination}</output>} />
                ))}
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </React.StrictMode>
    );
  });
  return container;
};

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('ProtectedRoute', () => {
  it('coalesces StrictMode replay while /me is pending, then passes its user through once', async () => {
    let resolveMe;
    const response = new Promise((resolve) => { resolveMe = resolve; });
    const user = { id: 7, name: 'Ada', roles: ['ANALISTA'] };
    apiRequest.mockReturnValue(response);
    const Dashboard = ({ user: authenticatedUser }) => (
      <div data-testid="dashboard-user">{authenticatedUser?.name}</div>
    );

    const view = await renderRoute('/dashboard', <ProtectedRoute><Dashboard /></ProtectedRoute>);

    expect(view.querySelector('.dashboard-skeleton')?.getAttribute('data-variant')).toBe('neutral');
    expect(view.querySelector('[role="progressbar"]')).toBeNull();
    expect(apiRequest).toHaveBeenCalledTimes(1);

    await act(async () => resolveMe({ ok: true, data: { user } }));

    expect(view.querySelector('[data-testid="dashboard-user"]')?.textContent).toBe('Ada');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('uses the resolved role for a suspended dashboard entry', async () => {
    let resolveMe;
    const response = new Promise((resolve) => { resolveMe = resolve; });
    apiRequest.mockReturnValue(response);
    const SuspendedDashboard = lazy(() => new Promise(() => {}));
    const view = await renderRoute(
      '/dashboard',
      <ProtectedRoute><SuspendedDashboard /></ProtectedRoute>
    );

    await act(async () => resolveMe({
      ok: true,
      data: { user: { id: 12, roles: ['RECEPCION'] } },
    }));

    expect(view.querySelector('.dashboard-skeleton')?.getAttribute('data-variant'))
      .toBe('reception');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['unauthenticated', '/dashboard', false, true, null, '/login'],
    ['connection error', '/dashboard', false, true, null, '/login'],
    ['non-admin', '/dashboard', true, true, { is_staff: false }, '/dashboard'],
    ['no purchase', '/dashboard', false, true, { service_status: 'NO_PURCHASED' }, '/no-purchased'],
    ['pending', '/dashboard', false, true, { service_status: 'PENDING' }, '/pending'],
    ['purchased', '/no-purchased', false, false, { service_status: 'COMPLETED' }, '/dashboard'],
    ['completed', '/pending', false, false, { service_status: 'COMPLETED' }, '/dashboard'],
  ])('preserves the %s redirect without mounting protected content', async (_name, path, requireAdmin, requireService, user, destination) => {
    apiRequest.mockResolvedValue({ ok: !!user, status: user ? 200 : _name === 'connection error' ? 0 : 401, data: { user } });
    // Admin-only paths must not overlap their dashboard redirect destination.
    const entry = requireAdmin ? '/admin' : path;
    const view = await renderRoute(entry, (
      <ProtectedRoute requireAdmin={requireAdmin} requireService={requireService}>
        <div data-testid="protected-content" />
      </ProtectedRoute>
    ));
    expect(view.querySelector('[data-testid="protected-content"]')).toBeNull();
    expect(view.textContent).toBe(destination);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['/dashboard', { is_staff: true }, true, true],
    ['/dashboard', { service_status: 'COMPLETED' }, false, true],
    ['/profile', { service_status: 'NO_PURCHASED' }, false, false],
    ['/no-purchased', { service_status: 'NO_PURCHASED' }, false, false],
    ['/pending', { service_status: 'PENDING' }, false, false],
  ])('retains access for %s with user %j', async (path, user, requireAdmin, requireService) => {
    apiRequest.mockResolvedValue({ ok: true, data: user });
    const view = await renderRoute(path, (
      <ProtectedRoute requireAdmin={requireAdmin} requireService={requireService}>
        <div data-testid="protected-content">Allowed</div>
      </ProtectedRoute>
    ));
    expect(view.textContent).toBe('Allowed');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('reuses the guard user across nested pages and a separately mounted protected route', async () => {
    const user = { name: 'Ada', roles: ['ANALISTA'], service_status: 'COMPLETED' };
    apiRequest.mockResolvedValue({ ok: true, data: { user } });
    const Page = ({ to }) => {
      const session = useSession();
      return <><output>{session.user?.name}</output><Link to={to}>Next</Link></>;
    };
    const view = await renderRoute('/dashboard', (
      <Routes>
        <Route path="/" element={<ProtectedRoute><Page to="/dashboard/rasgos" /></ProtectedRoute>} />
        <Route path="rasgos" element={<ProtectedRoute><Page to="/dashboard/profile" /></ProtectedRoute>} />
        <Route path="profile" element={<ProtectedRoute requireService={false}><Page to="/dashboard" /></ProtectedRoute>} />
      </Routes>
    ));
    for (let index = 0; index < 3; index += 1) {
      expect(view.querySelector('output').textContent).toBe('Ada');
      await act(async () => view.querySelector('a').click());
    }
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('rechecks a previous failed session before deciding whether a newly mounted guard can render', async () => {
    apiRequest.mockResolvedValueOnce({ ok: false, status: 0, data: {} })
      .mockResolvedValue({ ok: true, data: { user: { name: 'Ada' } } });
    const Entry = () => {
      const [enter, setEnter] = React.useState(false);
      useSession();
      return <>
        <button onClick={() => setEnter(true)}>Enter</button>
        {enter && <ProtectedRoute><div>Secret</div></ProtectedRoute>}
      </>;
    };
    const view = await renderRoute('/dashboard', <Entry />);
    await act(async () => view.querySelector('button').click());
    expect(view.textContent).toContain('Secret');
    expect(view.textContent).not.toContain('/login');
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it('recomputes admin authorization when the guard requirements change without another ME request', async () => {
    apiRequest.mockResolvedValue({ ok: true, data: { user: { is_staff: false } } });
    const Gate = () => {
      const [requireAdmin, setRequireAdmin] = React.useState(false);
      return <>
        <button onClick={() => setRequireAdmin(true)}>Admin only</button>
        <ProtectedRoute requireAdmin={requireAdmin}><div>Secret</div></ProtectedRoute>
      </>;
    };
    const view = await renderRoute('/admin', <Gate />);
    expect(view.textContent).toContain('Secret');
    await act(async () => view.querySelector('button').click());
    expect(view.textContent).toBe('/dashboard');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('removes protected content immediately when clearToken starts, without accepting a cached user', async () => {
    apiRequest.mockResolvedValue({ ok: true, data: { user: { name: 'Ada' } } });
    const view = await renderRoute('/dashboard', <ProtectedRoute><div>Secret</div></ProtectedRoute>);
    expect(view.textContent).toBe('Secret');
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    await act(async () => { void clearToken(); });
    expect(view.textContent).toBe('/login');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('does not show a dashboard skeleton while a non-dashboard route is authenticating', async () => {
    apiRequest.mockReturnValue(new Promise(() => {}));
    const view = await renderRoute('/profile', <ProtectedRoute><div>Profile</div></ProtectedRoute>);

    expect(view.querySelector('.dashboard-skeleton')).toBeNull();
    expect(view.textContent).toBe('');
  });
});
