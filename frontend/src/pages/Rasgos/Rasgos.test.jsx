import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { AuthProvider } from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/ProtectedRoute';
import Rasgos from './Rasgos';


vi.mock('../../hooks/useLatestGenomicsResults', async (importOriginal) => ({
  ...await importOriginal(), useLatestGenomicsResults: vi.fn(),
}));
// The overview/category swap waits for its exit animation; tests read the result, not the motion.
vi.mock('motion/react', async (importOriginal) => ({
  ...await importOriginal(), AnimatePresence: ({ children }) => children,
}));
vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(), apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('../../components/ResultsBar/ResultsBar', async () => {
  const { RESULT_MODULES, GUIDE_HREF } = await import('../../config/resultNav');
  return {
    default: ({ user, onLogout }) => (
      <nav aria-label="Dashboard navigation">
        <span>{user?.name}</span>
        {[...RESULT_MODULES, { href: GUIDE_HREF, name: 'Guía de módulos' }].map((m) => <Link key={m.href} to={m.href}>{m.name}</Link>)}
        <button type="button" onClick={onLogout}>Cerrar sesión</button>
      </nav>
    ),
  };
});

const disclaimer = 'Resultados de desarrollo. Solo el riesgo monogénico usa datos reales de ClinVar; '
  + 'el resto es simulado y no tiene valor clínico.';
const makeTrait = (result = 'Rápido', overrides = {}) => ({
  trait: 'cafeina', label: 'Metabolismo de la cafeína', category: 'Metabolismo', gene: 'CYP1A2', rsid: 'rs762551',
  description: 'CYP1A2 elimina la cafeína.', result, explanation: `Eliminas la cafeína ${result.toLowerCase()}.`,
  simulated: true, ...overrides,
});
const makeState = () => ({
  status: 'ready', loading: false, error: null, retry: vi.fn(),
  data: { disclaimer, sample_code: 'SEED-1', modules: { traits: [makeTrait()] } },
});

let state;
let root;
let container;
let originalInnerWidth;
function LocationMarker() {
  return <output aria-label="Current route">{useLocation().pathname}</output>;
}
const renderPage = async ({ protectedRoute = false } = {}) => {
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/dashboard/rasgos']}>
      <AuthProvider>
        {protectedRoute ? (
          <React.StrictMode><ProtectedRoute><Rasgos /></ProtectedRoute></React.StrictMode>
        ) : <Rasgos />}
        <LocationMarker />
      </AuthProvider>
    </MemoryRouter>
  ));
};
const getStatus = () => container.querySelector('main [role="status"], main [role="alert"]');
const getRetry = () => [...container.querySelectorAll('main button')]
  .find((button) => button.textContent === 'Reintentar');
const expectNeutralCopy = () => {
  // the page's own words: the bar on top carries the client's name, not result copy
  const copy = container.querySelector('main').cloneNode(true);
  copy.querySelector('nav[aria-label="Dashboard navigation"]')?.remove();
  const accessibleCopy = [...copy.querySelectorAll('[aria-label], [aria-description], [aria-valuetext], [title], [alt]')]
    .flatMap((node) => ['aria-label', 'aria-description', 'aria-valuetext', 'title', 'alt']
      .map((attribute) => node.getAttribute(attribute) || '')).join(' ');
  expect(`${copy.textContent} ${accessibleCopy}`).not.toMatch(
    /demo|demostraci[oó]n|sint[eé]tic[oa]s?|synthetic|no[\s_-]+evaluad[oa]s?|not[\s_-]+evaluated|no cl[ií]nic[oa]s?|non[\s_-]+clinical|sin revisi[oó]n cl[ií]nica|arbitrari[oa]s?/i
  );
};
const expectNoValues = () => expect(container.querySelector('.rasgos-trait')).toBeNull();
const categoryButtons = () => [...container.querySelectorAll('.rasgos-overview__legend-item')];
const openCategory = async (name = 'Metabolismo') => {
  await act(async () => categoryButtons().find((button) => button.textContent.includes(name)).click());
};
const expectShell = () => {
  expect(container.querySelector('h1')).not.toBeNull();
  expect(container.querySelector('h1').textContent).toBe('Lo que te hace tú');
  expect(container.querySelector('main.rasgos-layout__main')).not.toBeNull();
  expect(container.querySelector('nav[aria-label="Dashboard navigation"]')).not.toBeNull();
  expectNeutralCopy();
};

beforeEach(() => {
  vi.resetAllMocks();
  // jsdom lacks ResizeObserver, which the category pie chart needs to size itself.
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  state = makeState();
  useLatestGenomicsResults.mockImplementation(() => state);
  apiRequest.mockResolvedValue({ ok: true, data: { user: { name: 'Demo account' } } });
  originalInnerWidth = window.innerWidth;
  window.innerWidth = 1440;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  window.innerWidth = originalInnerWidth;
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
});

describe('traits results', () => {
  it('shows trait results without the ready banner or summary disclaimer', async () => {
    state.data.modules.traits = [makeTrait('Rápido', {
      options: [{ result: 'Rápido', frequency: 0.5 }, { result: 'Lento', frequency: 0.48 }],
    })];
    await renderPage();
    expectShell();
    expect(categoryButtons().map((button) => button.getAttribute('aria-label')))
      .toEqual(['Abrir categoría Metabolismo, 1 rasgo']);
    expect(container.querySelector('.rasgos-overview__chart').getAttribute('aria-label'))
      .toBe('Distribución de rasgos por categoría. Total: 1 rasgo.');
    expectNoValues();
    expect(container.querySelector('.rasgos-report__intro, .rasgos-disclaimer')).toBeNull();
    expect(container.textContent).not.toContain(disclaimer);
    expect(getRetry()).toBeUndefined();
    await openCategory();
    expect(container.querySelector('#traits-title').textContent).toBe('Metabolismo');
    expect(container.querySelector('.rasgos-trait__title').textContent).toBe('Metabolismo de la cafeína');
    expect(container.querySelector('.rasgos-trait__result').textContent).toBe('RápidoComo el 51% de las personas');
    const texts = (selector) => [...container.querySelectorAll(selector)].map((node) => node.textContent);
    expect(texts('.rasgos-bars__label')).toEqual(['RápidoTú', 'Lento']);
    expect(texts('.rasgos-bars__value')).toEqual(['51%', '49%']);
    const rows = [...container.querySelectorAll('.rasgos-bars__row')];
    expect(rows.map((row) => [row.getAttribute('aria-label'), row.className.includes('is-mine'), row.tabIndex]))
      .toEqual([
        ['Rápido: 51% de las personas · tu resultado', true, 0],
        ['Lento: 49% de las personas', false, 0],
      ]);
    expect([...container.querySelectorAll('.rasgos-bars__fill')].map((fill) => fill.style.width)).toEqual(['51%', '49%']);
    expect(texts('.rasgos-bars__tip')).toEqual(['51% de las personas · tu resultado', '49% de las personas']);
    expect(container.querySelector('.rasgos-bars figcaption').textContent)
      .toBe('Cómo se reparte Metabolismo de la cafeína en las personas');
    expect(container.querySelector('.rasgos-trait__explanation').textContent).toBe('Eliminas la cafeína rápido.');
    expect(container.querySelector('.rasgos-trait__about')).toBeNull();
    expect(container.querySelector('.rasgos-trait__gene').textContent).toContain('Gen CYP1A2');
    expect(container.querySelector('.rasgos-trait__gene').textContent).toContain('rs762551');
    const geneName = container.querySelector('.rasgos-gene-tip__name');
    const tip = document.getElementById(geneName.getAttribute('aria-describedby'));
    expect(geneName.textContent).toBe('CYP1A2');
    expect(tip.getAttribute('role')).toBe('tooltip');
    expect(tip.textContent).toBe('Qué hace CYP1A2CYP1A2 elimina la cafeína.');
    expect(container.querySelector('.rasgos-detail__pager')).toBeNull();
    expect(container.querySelector('.rasgos-report__intro, .rasgos-disclaimer')).toBeNull();
  });

  it('reuses the StrictMode guard profile and retains it after the result page remounts', async () => {
    await renderPage({ protectedRoute: true });
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.ME, { method: 'GET' });
  });

  it('uses the normalized hook while requesting only the shared ME profile', async () => {
    await renderPage();
    expect(useLatestGenomicsResults).toHaveBeenCalled();
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it('groups traits by category in the canonical order and returns to the overview', async () => {
    state.data.modules.traits = [
      makeTrait('Liso', { trait: 'cabello', label: 'Tipo de cabello', category: 'Apariencia Física' }),
      makeTrait('Rápido'),
      makeTrait('Tolerante', { trait: 'lactosa', label: 'Tolerancia a la lactosa' }),
      makeTrait('Raro', { trait: 'nuevo', label: 'Rasgo nuevo', category: undefined }),
    ];
    await renderPage();
    expect(categoryButtons().map((button) => button.getAttribute('aria-label'))).toEqual([
      'Abrir categoría Metabolismo, 2 rasgos', 'Abrir categoría Apariencia Física, 1 rasgo',
      'Abrir categoría Otros rasgos, 1 rasgo',
    ]);
    await openCategory('Metabolismo');
    const titles = () => [...container.querySelectorAll('.rasgos-trait__title')].map((title) => title.textContent);
    expect(titles()).toEqual(['Metabolismo de la cafeína', 'Tolerancia a la lactosa']);
    // Without options there is no comparison bar, only the plain result.
    expect(container.querySelector('.rasgos-trait__result').textContent).toBe('Rápido');
    expect(container.querySelector('.rasgos-bars')).toBeNull();
    const tabs = () => [...container.querySelectorAll('.rasgos-tabs__tab')];
    expect(tabs().map((tab) => [tab.textContent, tab.getAttribute('aria-current')])).toEqual([
      ['Metabolismo', 'true'], ['Apariencia Física', null], ['Otros rasgos', null],
    ]);
    await act(async () => tabs()[1].click());
    expect(container.querySelector('#traits-title').textContent).toBe('Apariencia Física');
    expect(titles()).toEqual(['Tipo de cabello']);
    await act(async () => tabs()[2].click());
    expect(container.querySelector('#traits-title').textContent).toBe('Otros rasgos');
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Todas las categorías')).click());
    expectNoValues();
    expect(categoryButtons()).toHaveLength(3);
  });

  it('reports a missing module when the service only has other results', async () => {
    state.data.modules = { pharmacogenetics: [{ gene: 'CYP2D6', diplotype: '*1/*1', phenotype: 'Normal', drugs: [] }] };
    await renderPage();
    expectNoValues();
    expect(getStatus().textContent).toContain('no tiene resultados de rasgos');
  });
});

const stateCases = [
  ['loading', { status: 'loading', loading: true, data: null }, 'Cargando tus rasgos', 'status'],
  ['empty', { status: 'empty', data: null }, 'Aún no tienes resultados', 'status'],
  ['permission', { status: 'permission', data: null, error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['unauthenticated', { status: 'permission', data: null, error: { status: 401 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', data: null, error: { kind: 'connection', status: 0 } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', data: null, error: { kind: 'http', status: 500 } }, 'No fue posible cargar', 'alert'],
  ['invalid response error', { status: 'error', data: null, error: { kind: 'invalid_data' } }, 'No fue posible cargar', 'alert'],
];
describe('result states and preserved independent shell', () => {

  it.each(stateCases)('keeps neutral status copy and ME profile in %s without stale values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoValues();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    const loading = override.status === 'loading';
    expect(getStatus().getAttribute('aria-busy')).toBe(String(loading));
    if (loading) {
      expect(getStatus().querySelector('.rasgos-loading__donut')).not.toBeNull();
      expect(getStatus().querySelectorAll('.rasgos-loading__row')).toHaveLength(5);
      expect(getStatus().querySelector('.rasgos-overview')?.getAttribute('aria-hidden')).toBe('true');
    } else {
      expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    }
    expect(Boolean(getRetry())).toBe(!loading);
    if (!loading) expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(container.textContent).not.toMatch(/predisposición|sin riesgo|no se encontraron|no tienes rasgos/i);
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(['empty', 'permission', 'connection error'])('uses only the named hook retry in %s', async (name) => {
    Object.assign(state, stateCases.find(([key]) => key === name)[1]);
    await renderPage();
    expect(getRetry().tagName).toBe('BUTTON');
    expect(getRetry().type).toBe('button');
    getRetry().focus();
    expect(document.activeElement).toBe(getRetry());
    await act(async () => getRetry().click());
    expect(state.retry).toHaveBeenCalledTimes(1);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('retries missing traits and shows only the newly loaded results', async () => {
    state.data.modules.traits = [];
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados de rasgos');
    const retry = state.retry;
    retry.mockImplementation(() => { state = { ...state, status: 'loading', loading: true, data: null, service: null }; });
    await act(async () => getRetry().click());
    await renderPage();
    expectNoValues();
    expectShell();
    expect(getStatus().textContent).toContain('Cargando tus rasgos');
    state = makeState();
    state.data.modules.traits = [makeTrait('Lento')];
    await renderPage();
    expect(getRetry()).toBeUndefined();
    await openCategory();
    expect(container.querySelector('.rasgos-trait__result strong').textContent).toBe('Lento');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('treats an empty traits module as missing', async () => {
    state.data.modules = { traits: [] };
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados de rasgos');
    expectNoValues();
    expectShell();
  });

  it.each([{ user: { name: 'Wrapped profile' } }, { name: 'Direct profile' }])('preserves ME response shape %j', async (data) => {
    state.status = 'permission';
    apiRequest.mockResolvedValue({ ok: true, data });
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain(data.user?.name || data.name);
    expect(getStatus().textContent).toContain('No tienes permiso');
  });

  it('does not turn a failed ME response into a traits failure', async () => {
    apiRequest.mockResolvedValue({ ok: false, data: null });
    await renderPage();
    await openCategory();
    expect(container.querySelector('.rasgos-trait__result strong').textContent).toBe('Rápido');
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps only retained navigation links in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/farmacogenetica', '/dashboard/rasgos',
      '/dashboard/enfermedades#polygenic_risk', '/dashboard/enfermedades#monogenic_risk', '/dashboard/modulos',
    ]);
    await act(async () => container.querySelector('a[href="/dashboard/ancestria"]').click());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/ancestria');
    expectShell();
  });

  it.each(['ready', 'loading', 'permission', 'error'])('clears the shared session once and navigates home on logout in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    await act(async () => [...container.querySelectorAll('nav button')].find((button) => button.textContent === 'Cerrar sesión').click());
    expect(apiRequest.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(0);
    expect(clearToken).toHaveBeenCalledExactlyOnceWith();
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/');
  });

  it('awaits shared logout and navigates home even when the server returns an error', async () => {
    const { clearToken: clearSession } = await vi.importActual('../../config/api');
    let finishLogout;
    const logoutFetch = vi.fn(async (url) => url === API_ENDPOINTS.LOGOUT
      ? new Promise((resolve) => { finishLogout = resolve; }) : new Response('{}'));
    vi.stubGlobal('fetch', logoutFetch);
    clearToken.mockImplementationOnce(clearSession);
    try {
      await renderPage();
      await act(async () => [...container.querySelectorAll('nav button')].find((button) => button.textContent === 'Cerrar sesión').click());
      expect(clearToken).toHaveBeenCalledExactlyOnceWith();
      expect(container.querySelector('nav').textContent).not.toContain('Demo account');
      expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/rasgos');
      await act(async () => finishLogout(new Response('{}', { status: 503 })));
      expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/');
      expect(clearToken).toHaveBeenCalledTimes(1);
      expect(logoutFetch.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(1);
      expect(apiRequest.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
