import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Dashboard from './Dashboard';

vi.mock('../../components/GridBento/GridBento', () => ({
  default: ({ cards }) => <div>{cards.map((card) => (
    <article key={card.id} id={card.id}><a href={card.cta.href}>{card.title}</a></article>
  ))}</div>,
}));
vi.mock('../../components/Sidebar/Sidebar', () => ({
  default: ({ items }) => <nav>{items.map((item) => (
    <a key={item.href} href={item.href}>{item.label}</a>
  ))}</nav>,
}));

const unavailableMessage = 'El reporte PDF estará disponible cuando los resultados hayan sido revisados y publicados. No se genera un PDF de demostración.';
const originalWidth = window.innerWidth;
let container;
let root;

const renderDashboard = async (width = 1440) => {
  window.innerWidth = width;
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<Dashboard user={{ first_name: 'Test' }} onLogout={vi.fn()} />);
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
  window.innerWidth = originalWidth;
  vi.unstubAllGlobals();
});

describe('Dashboard result navigation', () => {
  it.each([1440, 390])('offers only retained cards and sidebar destinations at width %i', async (width) => {
    const view = await renderDashboard(width);
    const expectedPaths = [
      '/dashboard/ancestria', '/dashboard/rasgos',
      '/dashboard/farmacogenetica', '/dashboard/enfermedades',
    ];
    expect([...view.querySelectorAll('main article a')].map((link) => link.getAttribute('href')))
      .toEqual(expectedPaths);
    expect([...view.querySelectorAll('aside nav a')].map((link) => link.getAttribute('href')))
      .toEqual([...expectedPaths, '/dashboard/modulos']);
    expect(view.querySelector('#postlogin-biomarcadores, #postlogin-biometricas')).toBeNull();
  });
});

describe('Dashboard PDF availability', () => {
  it('shows a persistent accessible explanation without generating a demo PDF', async () => {
    const view = await renderDashboard();
    const notice = view.querySelector('main [role="status"]');

    expect(notice).not.toBeNull();
    expect(notice.tagName).toBe('P');
    expect(notice.textContent).toBe(unavailableMessage);
    expect(notice.closest('[hidden], [aria-hidden="true"]')).toBeNull();
    expect(window.getComputedStyle(notice).display).not.toBe('none');
    expect(window.getComputedStyle(notice).visibility).not.toBe('hidden');
  });

  it.each([1440, 390])('exposes no PDF control or request at viewport width %i', async width => {
    const view = await renderDashboard(width);
    const reportControls = [...view.querySelectorAll('button, a, [role="button"]')]
      .filter(element => /descargar|generando|pdf|reporte/i.test(
        `${element.textContent} ${element.getAttribute('aria-label') || ''}`,
      ));

    expect(reportControls).toEqual([]);
    expect(view.querySelector('[download], a[href*=".pdf"], a[href*="/report/pdf"]')).toBeNull();
    expect(view.querySelector('[role="dialog"], .modal-overlay')).toBeNull();

    const notice = view.querySelector('[role="status"]');
    expect(notice).not.toBeNull();
    expect(notice.querySelector('button, a, [role="button"]')).toBeNull();
    await act(async () => {
      notice.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      notice.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    });

    expect(fetch).not.toHaveBeenCalled();
    expect(notice.textContent).toBe(unavailableMessage);
  });
});
