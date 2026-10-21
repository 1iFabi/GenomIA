import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import Dashboard from './Dashboard';

const helix = vi.hoisted(() => ({ props: null, dive: null }));
const results = vi.hoisted(() => ({ value: null }));

vi.mock('../../components/DnaHelix/DnaHelix', async () => {
  const { forwardRef, useImperativeHandle } = await import('react');
  return {
    default: forwardRef((props, ref) => {
      helix.props = props;
      useImperativeHandle(ref, () => ({ dive: helix.dive }));
      return <div data-testid="helix" />;
    }),
  };
});
const lines = vi.hoisted(() => ({ onLine: null }));
vi.mock('./HelixMessages', () => ({
  default: (props) => {
    lines.onLine = props.onLine;
    return null;
  },
}));
vi.mock('../../hooks/useLatestGenomicsResults', () => ({
  useLatestGenomicsResults: () => results.value,
}));

const unavailableMessage = 'El reporte PDF estará disponible cuando los resultados hayan sido revisados y publicados. No se genera un PDF de demostración.';
const originalWidth = window.innerWidth;
let container;
let root;

const Where = () => <p data-testid="where">{useLocation().pathname + useLocation().hash}</p>;

const renderDashboard = async (width = 1440) => {
  window.innerWidth = width;
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard user={{ first_name: 'Test' }} onLogout={vi.fn()} />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    );
  });
  return container;
};

beforeEach(() => {
  sessionStorage.clear();
  results.value = { status: 'empty', data: null, retry: vi.fn() };
  helix.dive = vi.fn(() => Promise.resolve());
});

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

const paths = [
  '/dashboard/ancestria', '/dashboard/farmacogenetica', '/dashboard/rasgos',
  '/dashboard/enfermedades#polygenic_risk', '/dashboard/enfermedades#monogenic_risk',
];
const enterLink = (view) => view.querySelector('main a.hx__enter');

describe('Dashboard result navigation', () => {
  it('greets the client and keeps the account behind the three-line button, top right', async () => {
    const view = await renderDashboard();
    const toggle = view.querySelector('.hx__bar button[aria-controls]');
    expect(view.querySelector('.hx__hello').textContent).toBe('Hola, Test');
    expect(view.querySelector('aside')).toBeNull();
    expect(toggle.getAttribute('aria-label')).toBe('Abrir menú');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    await act(async () => toggle.click());
    const menu = document.getElementById(toggle.getAttribute('aria-controls'));
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    // the modules live on the helix and its legend; the menu is the account
    expect([...menu.querySelectorAll('a, button')].map((el) => el.textContent))
      .toEqual(['Mi cuenta', 'Ir al sitio de GenomIA', 'Cerrar sesión']);

    await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })));
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('chooses a module on the list without numbers and points the way in at it', async () => {
    const view = await renderDashboard();
    const list = [...view.querySelectorAll('main nav.hx__mods button')];
    // the phone shows short names; the full name stays each button's text
    expect(list.map((b) => b.querySelector('.hx__mod-full').textContent)).toEqual(['Ancestría', 'Farmacogenética', 'Rasgos', 'Riesgo poligénico', 'Riesgo monogénico']);
    expect(view.querySelector('kbd')).toBeNull();
    expect(enterLink(view).getAttribute('href')).toBe(paths[0]);
    expect(enterLink(view).textContent).toBe('Explora tus orígenes');
    // a legend, not a tab bar: no icons, each dot the colour of its stretch
    expect(list.some((b) => b.querySelector('svg'))).toBe(false);
    expect(list.map((b) => b.style.getPropertyValue('--dot'))).toEqual(['#9b72c9', '#a88d74', '#4f8fd6', '#e5874a', '#5aa874']);

    await act(async () => list[2].click());
    expect(list[2].getAttribute('aria-current')).toBe('true');
    expect(helix.props.slot).toBe(2);
    expect(view.querySelector('main h1').textContent).toBe('Lo que te hace tú');
    expect(enterLink(view).getAttribute('href')).toBe(paths[2]);
    expect(enterLink(view).textContent).toBe('Descubre tus rasgos');
    expect(view.querySelector('[aria-live="polite"]').textContent).toBe('Rasgos: Lo que te hace tú');
  });

  it('on the phone, scrolling the list picks the middle module and a tap on it enters', async () => {
    vi.stubGlobal('matchMedia', (q) => ({ matches: q === '(max-width: 860px)' }));
    const view = await renderDashboard(390);
    const list = [...view.querySelectorAll('main nav.hx__mods button')];
    const nav = view.querySelector('main nav.hx__mods');
    Object.defineProperty(nav.querySelector('li'), 'offsetHeight', { value: 160 });
    nav.scrollTop = 160 * 3 + 40;
    await act(async () => nav.dispatchEvent(new Event('scroll')));
    expect(helix.props.slot).toBe(3);
    expect(list[3].getAttribute('aria-current')).toBe('true');
    expect(list[3].querySelector('.hx__mod-go').textContent).toBe(enterLink(view).textContent);

    // a tap on another row only picks it; a tap on the picked row dives in
    await act(async () => list[1].click());
    expect(helix.props.slot).toBe(1);
    expect(helix.dive).not.toHaveBeenCalled();
    await act(async () => list[1].click());
    expect(helix.dive).toHaveBeenCalledTimes(1);
    expect(view.querySelector('[data-testid="where"]').textContent).toBe(paths[1]);
  });

  it('picks on the helix, and only the link enters, after the dive', async () => {
    const view = await renderDashboard();
    await act(async () => helix.props.onPick(3));
    expect(view.querySelector('main h1').textContent).toBe('Frente al promedio');
    expect(view.querySelector('[data-testid="where"]')).toBeNull();
    expect(helix.props.onEnter).toBeUndefined();

    await act(async () => enterLink(view).click());
    expect(helix.dive).toHaveBeenCalledTimes(1);
    expect(view.querySelector('[data-testid="where"]').textContent).toBe(paths[3]);
  });

  it('comes back to the module it left from', async () => {
    let view = await renderDashboard();
    await act(async () => helix.props.onPick(4));
    await act(async () => root.unmount());
    root = null;
    container.remove();

    view = await renderDashboard();
    expect(helix.props.slot).toBe(4);
    expect(view.querySelector('main h1').textContent).toBe('Gen por gen');
  });
});

describe('Dashboard reading line', () => {
  const line = (view) => view.querySelector('main .hx__line');

  it('leaves the title alone when the module has data', async () => {
    results.value = { status: 'ready', data: { modules: { global_ancestry: [{ group_label: 'Amerindio', proportion: 0.572 }] } }, retry: vi.fn() };
    const view = await renderDashboard();
    expect(line(view)).toBeNull();
  });

  it('says so while loading', async () => {
    results.value = { status: 'loading', data: null, retry: vi.fn() };
    const view = await renderDashboard();
    expect(line(view).getAttribute('aria-busy')).toBe('true');
    expect(line(view).textContent).toBe('Cargando tu resumen…');
  });

  it('offers a retry on error', async () => {
    const retry = vi.fn();
    results.value = { status: 'error', data: null, retry };
    const view = await renderDashboard();
    await act(async () => line(view).querySelector('button').click());
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('explains an empty module and an empty report', async () => {
    results.value = { status: 'ready', data: { modules: {} }, retry: vi.fn() };
    let view = await renderDashboard();
    expect(line(view).textContent).toBe('Este módulo no trae datos en tu informe.');
    await act(async () => root.unmount());
    root = null;
    container.remove();

    results.value = { status: 'empty', data: null, retry: vi.fn() };
    view = await renderDashboard();
    expect(line(view).textContent).toBe('Tus resultados aparecerán aquí cuando estén publicados.');
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

describe('Dashboard tour', () => {
  afterEach(() => vi.useRealTimers());

  it('turns to the next module only once Genomin has finished his line, and never before 15 s', async () => {
    vi.useFakeTimers();
    results.value = { status: 'ready', data: { modules: {} }, retry: vi.fn() };
    await renderDashboard();
    await act(async () => vi.advanceTimersByTimeAsync(10000)); // untouched: the tour starts and turns once
    const first = helix.props.slot;
    expect(first).not.toBe(0);

    act(() => lines.onLine('start'));
    await act(async () => vi.advanceTimersByTimeAsync(20000)); // a long line: the module waits for it
    expect(helix.props.slot).toBe(first);
    act(() => lines.onLine('end'));
    await act(async () => vi.advanceTimersByTimeAsync(1799)); // then a beat
    expect(helix.props.slot).toBe(first);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    const second = helix.props.slot;
    expect(second).not.toBe(first);

    act(() => lines.onLine('start'));
    await act(async () => vi.advanceTimersByTimeAsync(5000)); // a short line still leaves the module its 15 s
    act(() => lines.onLine('end'));
    await act(async () => vi.advanceTimersByTimeAsync(9999));
    expect(helix.props.slot).toBe(second);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    const third = helix.props.slot;
    expect(third).not.toBe(second);

    await act(async () => vi.advanceTimersByTimeAsync(14999)); // nothing said on this one: 15 s, then on
    expect(helix.props.slot).toBe(third);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(helix.props.slot).not.toBe(third);
  });
});
