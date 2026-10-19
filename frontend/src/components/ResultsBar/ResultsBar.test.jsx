import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import ResultsBar from './ResultsBar';
import { SLOT_KEY } from '../../config/resultNav';

let container;
let root;

const Where = () => {
  const { pathname, hash } = useLocation();
  return <p data-testid="where">{pathname + hash}</p>;
};

const render = async (at, onLogout = vi.fn()) => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[at]}>
        <ResultsBar user={{ first_name: 'Ana María' }} onLogout={onLogout} />
        <Where />
      </MemoryRouter>
    );
  });
  return container;
};

const current = (view) => view.querySelector('.rbar__mod[aria-current="page"] .rbar__full')?.textContent;

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  sessionStorage.clear();
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe('ResultsBar', () => {
  it('goes back to the helix and names only the module on show, remembering it for the way back', async () => {
    const view = await render('/dashboard/rasgos');
    expect(view.querySelector('a.rbar__back').getAttribute('href')).toBe('/dashboard');
    expect(view.querySelector('a.rbar__back').getAttribute('aria-label')).toBe('Volver a tu ADN');
    expect([...view.querySelectorAll('.rbar__mod')].map((a) => a.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/farmacogenetica', '/dashboard/rasgos',
      '/dashboard/enfermedades#polygenic_risk', '/dashboard/enfermedades#monogenic_risk',
    ]);
    expect(current(view)).toBe('Rasgos');
    expect(sessionStorage.getItem(SLOT_KEY)).toBe('2');
  });

  it('tells the two risk modules apart by the hash, poligénico when there is none', async () => {
    let view = await render('/dashboard/enfermedades');
    expect(current(view)).toBe('Riesgo poligénico');
    await act(async () => view.querySelector('a[href$="#monogenic_risk"]').click());
    expect(current(view)).toBe('Riesgo monogénico');
    expect(sessionStorage.getItem(SLOT_KEY)).toBe('4');
    await act(async () => root.unmount());
    container.remove();

    view = await render('/dashboard/modulos');
    expect(current(view)).toBeUndefined();
    expect(sessionStorage.getItem(SLOT_KEY)).toBe('4');
  });

  it('opens the account from the three-line button and closes it on Escape or outside', async () => {
    const onLogout = vi.fn();
    const view = await render('/dashboard/ancestria', onLogout);
    const toggle = view.querySelector('.acct__toggle');
    await act(async () => toggle.click());
    expect(view.querySelector('.acct__who').textContent).toBe('AnaCliente GenomIA');

    await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })));
    expect(view.querySelector('.acct__pop')).toBeNull();
    expect(document.activeElement).toBe(toggle);

    await act(async () => toggle.click());
    await act(async () => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })));
    expect(view.querySelector('.acct__pop')).toBeNull();

    await act(async () => toggle.click());
    await act(async () => [...view.querySelectorAll('.acct__item')].find((b) => b.textContent === 'Cerrar sesión').click());
    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(view.querySelector('.acct__pop')).toBeNull();
  });
});
