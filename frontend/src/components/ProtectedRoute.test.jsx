import React, { act, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { apiRequest } from '../config/api';
import ProtectedRoute from './ProtectedRoute';

vi.mock('../config/api', () => ({
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={`${path.split('/').slice(0, 2).join('/')}/*`} element={element} />
        </Routes>
      </MemoryRouter>
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
});

describe('ProtectedRoute', () => {
  it('shows a neutral dashboard shell while /me is pending, then passes its user through once', async () => {
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

  it('does not show a dashboard skeleton while a non-dashboard route is authenticating', async () => {
    apiRequest.mockReturnValue(new Promise(() => {}));
    const view = await renderRoute('/profile', <ProtectedRoute><div>Profile</div></ProtectedRoute>);

    expect(view.querySelector('.dashboard-skeleton')).toBeNull();
    expect(view.textContent).toBe('');
  });
});
