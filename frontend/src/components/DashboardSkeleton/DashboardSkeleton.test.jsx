import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import DashboardSkeleton, { DashboardPageSkeleton, SkeletonBlock } from './DashboardSkeleton';


let container;
let root;

const render = async (element) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(element));
  return container;
};

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
});

describe('DashboardSkeleton', () => {
  it.each(['user', 'neutral'])('shows the client stage on /dashboard for %s: five modules, no sidebar, no spinner', async (variant) => {
    const view = await render(<DashboardSkeleton variant={variant} />);
    expect(view.querySelector('.cskel-stage')?.getAttribute('aria-busy')).toBe('true');
    expect(view.querySelectorAll('.cskel-mod')).toHaveLength(5);
    expect(view.querySelector('.dashboard-skeleton__sidebar, [role="progressbar"]')).toBeNull();
    expect(view.textContent).not.toMatch(/Cargando panel/);
  });

  it('draws Rasgos with the very skeleton its page shows while results load, aligned to the overview', async () => {
    const view = await render(
      <MemoryRouter initialEntries={['/dashboard/rasgos']}>
        <DashboardSkeleton variant="neutral" pathname="/dashboard/rasgos" />
      </MemoryRouter>
    );
    expect(view.querySelector('.cskel-page')).toBeNull();
    expect(view.querySelector('.rbar__mod[aria-current="page"] .rbar__full')?.textContent).toBe('Rasgos');
    expect(view.querySelector('.rasgos-header__title')?.textContent).toBe('Lo que te hace tú');
    const loading = view.querySelector('.rasgos-loading');
    expect(loading.getAttribute('aria-busy')).toBe('true');
    expect(loading.querySelector('.rasgos-overview__pie.rasgos-loading__donut')).not.toBeNull();
    expect(loading.querySelectorAll('.rasgos-overview__legend-item')).toHaveLength(5);
  });

  it('draws Farmacogenética with the very skeleton its page shows while results load', async () => {
    const view = await render(
      <MemoryRouter initialEntries={['/dashboard/farmacogenetica']}>
        <DashboardSkeleton variant="neutral" pathname="/dashboard/farmacogenetica" />
      </MemoryRouter>
    );
    expect(view.querySelector('.cskel-page')).toBeNull();
    expect(view.querySelector('main h1')?.textContent).toBe('Tus remedios');
    const loading = view.querySelector('.pgx-loading');
    expect(loading.getAttribute('aria-busy')).toBe('true');
    expect(loading.querySelectorAll('.pgx-card--ghost')).toHaveLength(6);
  });

  it.each([
    // one globe for the desktop frame, one for the phone's, which carries the continent deck under it
    ['/dashboard/ancestria', 'ancestria', '.cskel-globe', 2],
    ['/dashboard/ancestria', 'ancestria', '.askel__phone .cdeck__card', 2],
    ['/dashboard/enfermedades', 'enfermedades', '.cskel-panel', 2],
    ['/dashboard/modulos', 'modulos', '.cskel-panel', 3],
  ])('draws %s like the result page: module bar, title and its own content', async (pathname, page, selector, count) => {
    const view = await render(<DashboardSkeleton variant="neutral" pathname={pathname} />);
    const root = view.querySelector('.cskel-page');
    expect(root?.getAttribute('data-page')).toBe(page);
    expect(root.querySelectorAll('.cskel-bar .cskel-disc')).toHaveLength(2);
    expect(root.querySelectorAll('.cskel-strand__dot')).toHaveLength(5);
    expect(root.querySelectorAll(selector)).toHaveLength(count);
    expect(view.querySelector('.dashboard-skeleton__sidebar, button, a')).toBeNull();
  });

  it('keeps the staff access list skeleton', async () => {
    const view = await render(<DashboardSkeleton variant="admin" pathname="/dashboard/admin/analysts" />);
    expect(view.querySelectorAll('.dashboard-skeleton__table-row--access')).toHaveLength(5);
  });

  it.each(['admin', 'analyst', 'reception'])('supports the %s dashboard variant', async (variant) => {
    const view = await render(<DashboardSkeleton variant={variant} />);

    expect(view.querySelector('.dashboard-skeleton')?.getAttribute('data-variant')).toBe(variant);
    expect(view.querySelector('.dashboard-skeleton__content')).not.toBeNull();
  });

  it('provides reusable accessible blocks and page loading wrappers', async () => {
    const view = await render(
      <DashboardPageSkeleton label="Cargando resultados">
        <SkeletonBlock className="report-row" />
      </DashboardPageSkeleton>
    );
    const status = view.querySelector('.dashboard-page-skeleton');

    expect(status?.getAttribute('role')).toBe('status');
    expect(status?.getAttribute('aria-busy')).toBe('true');
    expect(status?.querySelector('.dashboard-skeleton__announcement')?.textContent)
      .toBe('Cargando resultados');
    expect(status?.querySelector('.dashboard-page-skeleton__content')?.getAttribute('aria-hidden'))
      .toBe('true');
    expect(status?.querySelector('.dashboard-skeleton__block.report-row')?.getAttribute('aria-hidden'))
      .toBe('true');
  });

  it('selects one shared role variant using the dashboard routing precedence', () => {
    expect(DashboardSkeleton.getRoleVariant({ is_staff: true, is_analyst: true })).toBe('admin');
    expect(DashboardSkeleton.getRoleVariant({ roles: ['ANALISTA'] })).toBe('analyst');
    expect(DashboardSkeleton.getRoleVariant({ is_reception: true })).toBe('reception');
    expect(DashboardSkeleton.getRoleVariant({})).toBe('user');
  });
});
