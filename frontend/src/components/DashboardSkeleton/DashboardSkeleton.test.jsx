import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
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
  it('reserves exactly the four retained result cards for the user dashboard', async () => {
    const view = await render(<DashboardSkeleton variant="user" />);
    expect([...view.querySelectorAll('.dashboard-skeleton__card')].map((card) => (
      [...card.classList].find((className) => className.startsWith('dashboard-skeleton__card--'))
    ))).toEqual([
      'dashboard-skeleton__card--ancestria', 'dashboard-skeleton__card--rasgos',
      'dashboard-skeleton__card--farmacogenetica', 'dashboard-skeleton__card--enfermedades',
    ]);
  });



  it.each([
    ['/dashboard/ancestria', '.dashboard-skeleton__map-panel', 1],
    ['/dashboard/farmacogenetica', '.dashboard-skeleton__report-panel', 1],
    ['/dashboard/enfermedades', '.dashboard-skeleton__report-panel', 2],
    ['/dashboard/modulos', '.dashboard-skeleton__module-grid .dashboard-skeleton__report-panel', 4],
    ['/dashboard/admin/analysts', '.dashboard-skeleton__table-row--access', 5],
  ])('matches loading structure to %s before the page is ready', async (pathname, selector, count) => {
    const view = await render(<DashboardSkeleton variant="neutral" pathname={pathname} />);
    expect(view.querySelectorAll(selector)).toHaveLength(count);
    expect(view.querySelector('.dashboard-skeleton')?.getAttribute('data-page')).not.toBe('overview');
    expect(view.querySelector('[role="progressbar"], button, a')).toBeNull();
  });

  it.each(['user', 'admin', 'analyst', 'reception'])('supports the %s dashboard variant', async (variant) => {
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
