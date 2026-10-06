import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PostloginUser from './PostloginUser';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';

vi.mock('../../config/api', () => ({
  API_ENDPOINTS: { LOGOUT: '/logout' }, apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('./Dashboard', () => ({ default: ({ user, onLogout }) => (
  <>
    <div data-testid="user-home">{user?.id}</div>
    <button type="button" onClick={onLogout}>Cerrar sesión</button>
  </>
) }));
vi.mock('../Ancestria/Ancestria', () => ({ default: () => <div data-testid="ancestria" /> }));
vi.mock('../Rasgos/Rasgos', () => ({ default: () => <div data-testid="rasgos" /> }));
vi.mock('../Enfermedades/Enfermedades', () => ({ default: () => <div data-testid="enfermedades" /> }));
vi.mock('../Farmacogenetica/Farmacogenetica', () => ({ default: () => <div data-testid="farmacogenetica" /> }));
vi.mock('../Biomarcadores/Biomarcadores', () => ({ default: () => <div data-testid="biomarcadores" /> }));
vi.mock('../Biometrics/Biometrics', () => ({ default: () => <div data-testid="biometricas" /> }));

let container;
let root;
const renderRoute = async (path) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard/*" element={<PostloginUser user={{ id: 1 }} />} />
        <Route path="/" element={<div data-testid="public-home" />} />
      </Routes>
    </MemoryRouter>
  ));
  return container;
};
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container?.remove();
  container = null;
  vi.resetAllMocks();
});

describe('user logout', () => {
  it('clears the shared session once and navigates home without a direct logout POST', async () => {
    const view = await renderRoute('/dashboard');
    await act(async () => view.querySelector('button').click());
    expect(clearToken).toHaveBeenCalledExactlyOnceWith();
    expect(apiRequest.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(0);
    expect(view.querySelector('[data-testid="public-home"]')).not.toBeNull();
  });

  it('waits for shared best-effort logout to complete before navigating home', async () => {
    let finishLogout;
    clearToken.mockImplementationOnce(() => new Promise((resolve) => { finishLogout = resolve; }));
    const view = await renderRoute('/dashboard');
    await act(async () => view.querySelector('button').click());
    expect(clearToken).toHaveBeenCalledExactlyOnceWith();
    expect(view.querySelector('[data-testid="public-home"]')).toBeNull();
    await act(async () => finishLogout());
    expect(view.querySelector('[data-testid="public-home"]')).not.toBeNull();
    expect(clearToken).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(0);
  });
});

describe('user result routes', () => {
  it('passes updated guard user data through instead of retaining its initial snapshot', async () => {
    const view = await renderRoute('/dashboard');
    expect(view.querySelector('[data-testid="user-home"]').textContent).toBe('1');
    await act(async () => root.render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard/*" element={<PostloginUser user={{ id: 2 }} />} />
        </Routes>
      </MemoryRouter>
    ));
    expect(view.querySelector('[data-testid="user-home"]').textContent).toBe('2');
  });

  it.each(['biomarcadores', 'biometricas'])('does not register the retired %s route', async (path) => {
    const view = await renderRoute(`/dashboard/${path}`);
    expect(view.querySelector(`[data-testid="${path}"]`)).toBeNull();
    expect(view.childElementCount).toBe(0);
  });

  it.each([
    ['', 'user-home'], ['ancestria', 'ancestria'], ['rasgos', 'rasgos'],
    ['enfermedades', 'enfermedades'], ['farmacogenetica', 'farmacogenetica'],
  ])('preserves the retained /dashboard/%s route', async (path, marker) => {
    const view = await renderRoute(`/dashboard/${path}`);
    expect(view.querySelector(`[data-testid="${marker}"]`)).not.toBeNull();
  });
});
