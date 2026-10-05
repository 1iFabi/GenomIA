import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import PostloginRouter from './PostloginRouter';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import { useAdminStats } from '../../hooks/useAdminStats';
import { apiRequest } from '../../config/api';

vi.mock('../../config/api', () => ({
  API_ENDPOINTS: { ME: '/me', DASHBOARD: '/api/auth/dashboard/', LOGOUT: '/logout' },
  apiRequest: vi.fn(),
  clearToken: vi.fn(),
}));
vi.mock('./PostloginUser', () => ({ default: ({ user }) => <div data-testid="user-home">{user.id}</div> }));
vi.mock('./PostloginAdmin', () => ({ default: ({ user }) => <div data-testid="admin-home">{user.id}</div> }));
vi.mock('./PostloginAnalyst', () => ({ default: ({ user }) => <div data-testid="analyst-home">{user.id}</div> }));
vi.mock('./PostloginReception', () => ({ default: ({ user }) => <div data-testid="reception-home">{user.id}</div> }));
vi.mock('./AdminVariantsDatabase', () => ({ default: () => <div data-testid="admin-variants" /> }));
vi.mock('./AdminAnalystAccess', () => ({ default: () => <div data-testid="admin-analysts" /> }));
vi.mock('../Biomarcadores/Biomarcadores', () => ({ default: () => <div data-testid="biomarcadores" /> }));
vi.mock('../Biometrics/Biometrics', () => ({ default: () => <div data-testid="biometricas" /> }));
vi.mock('../Enfermedades/Enfermedades', () => ({ default: () => <div data-testid="enfermedades" /> }));
vi.mock('../Farmacogenetica/Farmacogenetica', () => ({ default: () => <div data-testid="farmacogenetica" /> }));
vi.mock('../../components/Nala/NalaWidget', () => ({ default: () => null }));

let container;
let root;

const LocationMarker = () => <output data-testid="location">{useLocation().pathname}</output>;
const StatsProbe = () => <output data-testid="stats">{JSON.stringify(useAdminStats())}</output>;

const renderView = async (element, path = '/dashboard') => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
    container?.remove();
  }
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        {element}
        <LocationMarker />
      </MemoryRouter>
    );
  });
  return container;
};

const renderDashboard = (user, path = '/dashboard') => {
  apiRequest.mockResolvedValue({ ok: true, data: { user: { id: -1 } } });
  return renderView(
    <Routes>
      <Route path="/dashboard/*" element={<PostloginRouter user={user} />} />
    </Routes>,
    path,
  );
};

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
  vi.clearAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('retired SNP catalog dashboard consumers', () => {
  const response = { ok: true, data: {
    total_users: 7, pending_reports: 3, analysis_count: 4, variants_count: 99,
  } };

  describe.each(['Admin', 'Analyst'])('%s dashboard', (role) => {
    const renderHome = async () => {
      const { default: Home } = await vi.importActual(`./Postlogin${role}.jsx`);
      apiRequest.mockResolvedValue(response);
      return renderView(<Home user={{ id: 1, username: 'Reviewer' }} />);
    };

    it('removes legacy catalog and report-file cards while preserving role navigation', async () => {
      const view = await renderHome();
      const main = view.querySelector('main');
      expect(main.textContent).not.toContain('Base de datos de variantes genéticas');
      expect(main.textContent).not.toContain('Ver variantes');
      expect(main.textContent).not.toContain('Administrar reportes genéticos');
      expect(main.textContent).not.toContain('Administrar archivo');
      const links = [...main.querySelectorAll('a')];
      expect(links.map((link) => link.textContent.trim())).toEqual(role === 'Admin'
        ? ['Gestionar permisos'] : []);
      if (role === 'Admin') {
        await act(async () => links[0].click());
        expect(view.querySelector('[data-testid="location"]').textContent).toBe('/dashboard/admin/analysts');
      } else {
        expect(main.querySelector('[aria-label="Administración"]')).toBeNull();
      }
    });

    it('removes the SNP statistic and preserves the three remaining values', async () => {
      const view = await renderHome();
      const section = view.querySelector('[aria-label="Estadísticas"]');
      expect(section.textContent).not.toContain('Variantes en BD');
      expect([...section.querySelectorAll('[class$="__stat-label"]')].map((node) => node.textContent))
        .toEqual(['Usuarios Totales', 'Reportes Pendientes', 'Análisis Completados']);
      expect([...section.querySelectorAll('[class$="__stat-value"]')].map((node) => node.textContent))
        .toEqual(['7', '3', '4']);
      expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/api/auth/admin/stats/', { method: 'GET' });
    });
  });

  it.each([
    ['admin', true, 1280], ['analyst', false, 1280],
    ['mobile admin', true, 768], ['mobile analyst', false, 768],
  ])('removes catalog navigation from the %s sidebar', async (_label, isAdmin, width) => {
    vi.stubGlobal('innerWidth', width);
    const closeMenu = vi.fn();
    const view = await renderView(<AdminSidebar isAdmin={isAdmin} isMobileMenuOpen setIsMobileMenuOpen={closeMenu} />);
    if (width > 1024) {
      await act(async () => view.querySelector('.admin-sidebar').dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    }
    const nav = view.querySelector('nav');
    expect(nav.querySelector('[href="#ver-variantes"]')).toBeNull();
    expect(nav.textContent).not.toContain('Ver variantes');
    const links = [...nav.querySelectorAll('a')];
    expect(nav.textContent).not.toContain('Administrar reportes genéticos');
    expect(links.map((link) => link.textContent.trim())).toEqual(isAdmin
      ? ['Otorgar permisos'] : []);
    if (isAdmin) {
      await act(async () => links[0].click());
      expect(view.querySelector('[data-testid="location"]').textContent).toBe('/dashboard/admin/analysts');
      if (width <= 1024) expect(closeMenu).toHaveBeenCalledWith(false);
    }
  });

  it('drops the SNP hook mapping from initial, loaded and refreshed stats without changing polling', async () => {
    vi.useFakeTimers();
    let resolveRequest;
    apiRequest.mockImplementationOnce(() => new Promise((resolve) => { resolveRequest = resolve; }));
    const view = await renderView(<StatsProbe />);
    const current = () => JSON.parse(view.querySelector('[data-testid="stats"]').textContent);
    expect(current().stats).not.toHaveProperty('variantsInDB');
    expect(current()).toMatchObject({ loading: true, error: null });
    await act(async () => resolveRequest(response));
    expect(current().stats).not.toHaveProperty('variantsInDB');
    expect(current()).toMatchObject({ stats: { totalUsers: 7, pendingReports: 3, completedAnalysis: 4 }, loading: false, error: null });
    apiRequest.mockResolvedValue({ ok: true, data: { total_users: 8, pending_reports: 2, analysis_count: 6 } });
    await act(async () => vi.advanceTimersByTimeAsync(60000));
    expect(current().stats).not.toHaveProperty('variantsInDB');
    expect(current().stats).toMatchObject({ totalUsers: 8, pendingReports: 2, completedAnalysis: 6 });
    expect(apiRequest).toHaveBeenCalledTimes(2);
    expect(apiRequest).toHaveBeenLastCalledWith('/api/auth/admin/stats/', { method: 'GET' });
    await act(async () => root.unmount());
    root = null;
    await vi.advanceTimersByTimeAsync(60000);
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });
});

describe('PostloginRouter', () => {
  describe.each([
    ['admin', { id: 1, is_staff: true }],
    ['analyst', { id: 2, roles: ['ANALISTA'] }],
  ])('%s result routes', (_role, user) => {
    it.each(['biomarcadores', 'biometricas'])('does not register the retired %s route', async (path) => {
      const view = await renderDashboard(user, `/dashboard/${path}`);
      expect(view.querySelector(`[data-testid="${path}"]`)).toBeNull();
      expect(view.querySelectorAll(':scope > :not([data-testid="location"])')).toHaveLength(0);
      expect(apiRequest).not.toHaveBeenCalled();
    });

    it('does not register the retired SNP catalog route', async () => {
      const view = await renderDashboard(user, '/dashboard/admin/variants');
      expect(view.querySelector('[data-testid="admin-variants"]')).toBeNull();
      expect(view.querySelectorAll(':scope > :not([data-testid="location"])')).toHaveLength(0);
      expect(apiRequest).not.toHaveBeenCalled();
    });

    it('does not mount the retired report-file page or request legacy APIs from its old URL', async () => {
      const view = await renderDashboard(user, '/dashboard/admin/reports');
      expect(view.querySelectorAll(':scope > :not([data-testid="location"])')).toHaveLength(0);
      expect(apiRequest).not.toHaveBeenCalled();
    });

    it.each([
      ['enfermedades', 'enfermedades'], ['farmacogenetica', 'farmacogenetica'],
    ])('preserves the retained %s route', async (path, marker) => {
      const view = await renderDashboard(user, `/dashboard/${path}`);
      expect(view.querySelector(`[data-testid="${marker}"]`)).not.toBeNull();
      expect(apiRequest).not.toHaveBeenCalled();
    });
  });

  it('routes the already-authenticated admin user without another /me request', async () => {
    const view = await renderDashboard({ id: 1, is_staff: true });

    expect(view.querySelector('[data-testid="admin-home"]')?.textContent).toBe('1');
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('selects the analyst dashboard from the passed user role', async () => {
    const view = await renderDashboard({ id: 2, roles: ['ANALISTA'] });

    expect(view.querySelector('[data-testid="analyst-home"]')?.textContent).toBe('2');
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('selects the reception dashboard from the passed user role', async () => {
    const view = await renderDashboard({ id: 3, roles: ['RECEPCION'] });

    expect(view.querySelector('[data-testid="reception-home"]')?.textContent).toBe('3');
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('preserves the default user dashboard and admin role-management route', async () => {
    const user = { id: 4, roles: [] };
    const view = await renderDashboard(user);

    expect(view.querySelector('[data-testid="user-home"]')?.textContent).toBe('4');

    const analysts = await renderDashboard({ id: 5, is_admin: true }, '/dashboard/admin/analysts');
    expect(analysts.querySelector('[data-testid="admin-analysts"]')).not.toBeNull();
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
