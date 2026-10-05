import React, { act } from 'react';
import { readFileSync } from 'node:fs';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import DashboardSkeleton, { DashboardPageSkeleton, SkeletonBlock } from './DashboardSkeleton';

const dashboardSkeletonStyles = readFileSync('src/components/DashboardSkeleton/DashboardSkeleton.css', 'utf8');
const dashboardGridStyles = readFileSync('src/components/GridBento/GridBento.css', 'utf8');

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
    ['skeleton', dashboardSkeletonStyles], ['grid', dashboardGridStyles],
  ])('removes retired slots from the %s layout at every desktop breakpoint', (_name, styles) => {
    expect(styles).not.toMatch(/biomarcadores|biometricas/);
    const templates = [...styles.matchAll(/grid-template-areas:\s*([^;]+);/g)]
      .map(([, value]) => [...value.matchAll(/['"]([^'"]+)['"]/g)].map(([, row]) => row));
    expect(templates).toEqual([[
      'ancestria rasgos farmacogenetica', 'ancestria enfermedades enfermedades',
    ]]);
    const rowCounts = [...styles.matchAll(/grid-template-rows:\s*repeat\((\d+),\s*1fr\);/g)]
      .map(([, count]) => Number(count));
    expect(rowCounts.length).toBeGreaterThan(0);
    expect(rowCounts.every((count) => count === 2)).toBe(true);
  });

  it('shimmers dashboard content instead of the sidebar and disables it for reduced motion', () => {
    expect(dashboardSkeletonStyles).toMatch(/\.dashboard-skeleton__content::after\s*\{/);
    expect(dashboardSkeletonStyles).not.toMatch(/\.dashboard-skeleton::after\s*\{/);
    expect(dashboardSkeletonStyles).toMatch(/\.dashboard-skeleton__content\s*\{[^}]*position:\s*relative;/);
    expect(dashboardSkeletonStyles).toMatch(/\.dashboard-skeleton__content::after\s*\{[^}]*background:\s*linear-gradient\([^;]*rgba\(15,\s*35,\s*65,\s*0\.1\)/);
    expect(dashboardSkeletonStyles).toMatch(/animation:\s*dashboard-skeleton-shimmer\s+2\.8s\s+linear\s+infinite/);
    expect(dashboardSkeletonStyles).toMatch(/\.dashboard-skeleton__content::after\s*\{[^}]*left:\s*0;/);
    expect(dashboardSkeletonStyles).toMatch(/@keyframes dashboard-skeleton-shimmer\s*\{\s*from\s*\{\s*transform:\s*translateX\(0(?:%|px)?\);/);
    expect(dashboardSkeletonStyles).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*\.dashboard-skeleton__content::after\s*\{[^}]*animation:\s*none;[^}]*opacity:\s*0;[^}]*\}\s*\}/);
  });

  it('renders a neutral structural shell without visible loading copy', async () => {
    const view = await render(<DashboardSkeleton variant="neutral" />);
    const shell = view.querySelector('.dashboard-skeleton');

    expect(shell?.getAttribute('data-variant')).toBe('neutral');
    expect(shell?.getAttribute('role')).toBe('status');
    expect(shell?.querySelector('.dashboard-skeleton__announcement')?.textContent)
      .toBe('Loading dashboard');
    expect(shell?.querySelector('.dashboard-skeleton__main')?.getAttribute('aria-hidden'))
      .toBe('true');
    expect(view.querySelector('.dashboard-skeleton__card-grid')).toBeNull();
    expect(view.querySelector('[role="progressbar"]')).toBeNull();
  });

  it.each(['user', 'admin', 'analyst', 'reception'])('supports the %s dashboard variant', async (variant) => {
    const view = await render(<DashboardSkeleton variant={variant} />);

    expect(view.querySelector('.dashboard-skeleton')?.getAttribute('data-variant')).toBe(variant);
    expect(view.querySelector('.dashboard-skeleton__content')).not.toBeNull();
  });

  it('provides reusable accessible blocks and page loading wrappers', async () => {
    const view = await render(
      <DashboardPageSkeleton label="Loading report">
        <SkeletonBlock className="report-row" />
      </DashboardPageSkeleton>
    );
    const status = view.querySelector('.dashboard-page-skeleton');

    expect(status?.getAttribute('role')).toBe('status');
    expect(status?.querySelector('.dashboard-skeleton__announcement')?.textContent)
      .toBe('Loading report');
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
