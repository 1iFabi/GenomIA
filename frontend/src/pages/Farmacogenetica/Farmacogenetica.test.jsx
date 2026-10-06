import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cwd } from 'node:process';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { AuthProvider } from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/ProtectedRoute';
import Farmacogenetica from './Farmacogenetica';

const pageStyles = readFileSync(resolve(cwd(), 'src/pages/Farmacogenetica/Farmacogenetica.css'), 'utf8');
vi.mock('../../hooks/useLatestGenomicsResults', () => ({ useLatestGenomicsResults: vi.fn() }));
vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(), apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('../../components/Sidebar/Sidebar', () => ({
  default: ({ items, onLogout, user, isMobileMenuOpen, setIsMobileMenuOpen }) => (
    <nav aria-label="Dashboard navigation" data-open={isMobileMenuOpen}>
      <span>{user?.name}</span>
      {items.map((item) => <Link key={item.href} to={item.href}>{item.label}</Link>)}
      <button type="button" onClick={onLogout}>Cerrar sesión</button>
      <button type="button" onClick={() => setIsMobileMenuOpen(false)}>Cerrar navegación</button>
    </nav>
  ),
}));
vi.mock('../../components/SunburstChart/SunburstChart', () => ({
  default: () => <div data-legacy-chart="true">Legacy chart</div>,
}));
vi.mock('../../components/GeneticTraitBar/GeneticTraitBar', () => ({
  default: () => <div data-legacy-trait="true">Legacy trait</div>,
}));

const provenance = {
  synthetic: true, non_clinical: true, clinically_reviewed: false, display_only: true,
  numeric_semantics: 'arbitrary_demo_only_not_evaluated',
};
const makeModule = () => ({
  module: 'pharmacogenetics', result_type: 'synthetic_placeholder', value_code: 'SYNTHETIC_NOT_EVALUATED',
  payload: {
    ...provenance, module: 'pharmacogenetics', state: 'not_evaluated', label: 'Demo interaction A',
    display: { kind: 'demo_interactions', items: [{ label: 'Demo interaction A', display_value: 8 }] },
  },
});
const makeState = () => ({
  status: 'ready', loading: false, service: { service_request_id: 'latest' }, error: null,
  data: { ...provenance, results: [makeModule()] }, retry: vi.fn(),
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
    <MemoryRouter initialEntries={['/dashboard/farmacogenetica']}>
      <AuthProvider>
        {protectedRoute ? (
          <React.StrictMode><ProtectedRoute><Farmacogenetica /></ProtectedRoute></React.StrictMode>
        ) : <Farmacogenetica />}
        <LocationMarker />
      </AuthProvider>
    </MemoryRouter>
  ));
};
const getStatus = () => container.querySelector('main [role="status"], main [role="alert"]');
const getRetry = () => [...container.querySelectorAll('main button')]
  .find((button) => button.textContent === 'Reintentar');
const expectNeutralCopy = () => {
  const copy = container.querySelector('main');
  const accessibleCopy = [...copy.querySelectorAll('[aria-label], [aria-description], [aria-valuetext], [title], [alt]')]
    .flatMap((node) => ['aria-label', 'aria-description', 'aria-valuetext', 'title', 'alt']
      .map((attribute) => node.getAttribute(attribute) || '')).join(' ');
  expect(`${copy.textContent} ${accessibleCopy}`).not.toMatch(
    /demo|demostraci[oó]n|sint[eé]tic[oa]s?|synthetic|no[\s_-]+evaluad[oa]s?|not[\s_-]+evaluated|no cl[ií]nic[oa]s?|non[\s_-]+clinical|sin revisi[oó]n cl[ií]nica|arbitrari[oa]s?/i
  );
};
const expectNoDisplay = () => {
  expect(container.querySelector('dl')).toBeNull();
  expect(container.textContent).not.toContain('Interacción A');
};
const expectShell = () => {
  expect(container.querySelector('.section-header h1').textContent).toBe('Farmacogenética');
  expect(container.querySelector('main.farmaco-main-content')).not.toBeNull();
  expect(container.querySelector('aside.farmaco-sidebar-area nav')).not.toBeNull();
  expectNeutralCopy();
};

beforeEach(() => {
  vi.resetAllMocks();
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

describe('normalized pharmacogenetics results', () => {
  it('shows the localized category and raw value without visible or accessible disclosure copy', async () => {
    const rawData = structuredClone(state.data);
    await renderPage();
    expectShell();
    expect(container.querySelector('dt').textContent).toBe('Interacción A');
    expect(state.data).toEqual(rawData);
    expect(container.querySelector('dd').textContent).toBe('8');
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.textContent).not.toMatch(/%|riesgo|precaución|supervisión|dosis|respuesta típica|tratamiento|rsid|genotipo|cromosoma|frecuencia|recomendación/i);
    expect(container.querySelector('[data-legacy-chart], [data-legacy-trait]')).toBeNull();
    expect(getStatus().textContent).toContain('disponibles');
  });

  it('reuses the StrictMode guard profile and retains it after the result page remounts', async () => {
    await renderPage({ protectedRoute: true });
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.ME, { method: 'GET' });
  });

  it('uses the normalized hook and requests only the shared ME profile', async () => {
    await renderPage();
    expect(useLatestGenomicsResults).toHaveBeenCalled();
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
    expect(container.querySelector('nav').textContent).toContain('Demo account');
  });

  it.each([0, -7.25, 137, 0.001, 1e100])('preserves raw finite value %s without units or conversion', async (value) => {
    state.data.results[0].payload.display.items[0].display_value = value;
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe(String(value));
    expect(container.textContent).not.toMatch(/%|mg|score|puntaje|probabilidad|riesgo/i);
  });

  it('shows only the validated display, never legacy fields or other modules', async () => {
    Object.assign(state.data.results[0].payload, {
      drugs: [{ name: 'Legacy drug' }], rsid: 'rs123', genotipo: 'AA', percentage: 99,
      freq_chile_percent: 87, cromosoma: 12, posicion: 345, magnitud: 'alto',
      dose_adjustment: 'Legacy advice', expected_response: 'Legacy response',
    });
    Object.assign(state.data.results[0].payload.display.items[0], {
      label: '  Demo label retained  ', unit: '%', interpretation: 'Legacy interpretation',
    });
    state.data.results[0].payload.display.items.push({ label: 'Demo interaction B', display_value: 6.75 });
    state.data.results.push(...['global_ancestry', 'local_ancestry', 'polygenic_risk', 'monogenic_risk', 'traits']
      .map((module) => ({ module, payload: { display: { items: [{ label: 'Other module', display_value: 99 }] } } })));
    await renderPage();
    expect([...container.querySelectorAll('dt')].map((item) => item.textContent)).toEqual(['  label retained  ', 'Interacción B']);
    expect([...container.querySelectorAll('dd')].map((item) => item.textContent)).toEqual(['8', '6.75']);
    expect(state.data.results[0].payload.display.items.map((item) => item.label)).toEqual(['  Demo label retained  ', 'Demo interaction B']);
    expectNeutralCopy();
    expect(container.textContent).not.toMatch(/Legacy|Other module|rs123|AA|99|87|345|%/);
  });

  it.each(['Etiqueta conservada', '  Etiqueta conservada  '])('preserves other usable display labels exactly: %s', async (label) => {
    state.data.results[0].payload.display.items[0].label = label;
    await renderPage();
    expect(container.querySelector('dt').textContent).toBe(label);
    expect(container.querySelector('dd').textContent).toBe('8');
    expectNeutralCopy();
  });

  it('keeps root and payload disclaimers internal while preserving values and provenance validation', async () => {
    state.data.disclaimer = 'Synthetic, non-clinical demonstration. Not evaluated.';
    state.data.results[0].payload.disclaimer = 'Do not borrow a payload disclaimer.';
    await renderPage();
    expectNeutralCopy();
    expect(container.textContent).not.toContain(state.data.disclaimer);
    expect(container.textContent).not.toContain('Do not borrow');
    expect(container.querySelector('.farmaco-demo-disclaimer')).toBeNull();
    expect(container.querySelector('dd').textContent).toBe('8');
    state.data.synthetic = false;
    await renderPage();
    expect(container.textContent).not.toContain(state.data.disclaimer);
    expectNoDisplay();
    expect(getStatus().getAttribute('role')).toBe('alert');
  });

  it.each([undefined, null, '', '  ', 8, {}])('does not invent a disclaimer when it is unusable: %j', async (disclaimer) => {
    state.data.disclaimer = disclaimer;
    state.data.results[0].payload.disclaimer = 'Unvalidated disclaimer';
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe('8');
    expect(container.querySelector('.farmaco-demo-disclaimer')).toBeNull();
    expect(container.textContent).not.toContain('Unvalidated disclaimer');
  });

  it('leaves v1 without a display unavailable instead of deriving a value', async () => {
    state.service.release_version = '1';
    delete state.data.results[0].payload.display;
    state.data.results[0].payload.rows = [{ label: 'Demo interaction A', value: null }];
    await renderPage();
    expectNoDisplay();
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expectShell();
  });

  it('does not borrow displays from other modules when pharmacogenetics is missing', async () => {
    state.data.results = [{ module: 'traits', payload: { display: { kind: 'demo_interactions', items: [{ label: 'Other module', display_value: 99 }] } } }];
    await renderPage();
    expectNoDisplay();
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getStatus().textContent).toContain('El módulo de farmacogenética no está disponible');
    expect(container.textContent).not.toMatch(/Other module|99/);
  });

  const invalidCases = [
    ['duplicate target', (data) => data.results.push(makeModule())],
    ['duplicate other module', (data) => data.results.push({ module: 'traits' }, { module: 'traits' })],
    ['unexpected module', (data) => data.results.push({ module: 'unexpected' })],
    ['malformed result', (data) => data.results.push(null)],
    ['missing module ID', (data) => data.results.push({})],
    ['missing results', (data) => { delete data.results; }],
    ['non-array results', (data) => { data.results = {}; }],
    ['missing payload', (data) => { delete data.results[0].payload; }],
    ['null payload', (data) => { data.results[0].payload = null; }],
    ['array payload', (data) => { data.results[0].payload = []; }],
    ['missing state', (data) => { delete data.results[0].payload.state; }],
    ['evaluated state', (data) => { data.results[0].payload.state = 'evaluated'; }],
    ['missing display', (data) => { delete data.results[0].payload.display; }],
    ['null display', (data) => { data.results[0].payload.display = null; }],
    ['array display', (data) => { data.results[0].payload.display = []; }],
    ['unexpected display kind', (data) => { data.results[0].payload.display.kind = 'demo_traits'; }],
    ['missing items', (data) => { delete data.results[0].payload.display.items; }],
    ['non-array items', (data) => { data.results[0].payload.display.items = {}; }],
    ['empty items', (data) => { data.results[0].payload.display.items = []; }],
    ['null item', (data) => { data.results[0].payload.display.items = [null]; }],
    ['array item', (data) => { data.results[0].payload.display.items = [[]]; }],
    ['missing label', (data) => { delete data.results[0].payload.display.items[0].label; }],
    ['blank label', (data) => { data.results[0].payload.display.items[0].label = ' '; }],
    ['non-text label', (data) => { data.results[0].payload.display.items[0].label = 8; }],
    ['missing value', (data) => { delete data.results[0].payload.display.items[0].display_value; }],
    ...[NaN, Infinity, -Infinity, '8', null, true, {}].map((value) => [
      `non-finite or non-numeric value ${String(value)}`,
      (data) => { data.results[0].payload.display.items[0].display_value = value; },
    ]),
    ['invalid second item', (data) => data.results[0].payload.display.items.push({ label: 'Demo interaction B', display_value: NaN })],
    ['duplicate item label', (data) => data.results[0].payload.display.items.push({ label: 'Demo interaction A', display_value: 9 })],
  ];
  it.each(invalidCases)('rejects %s without partial values or legacy fallback', async (_name, mutate) => {
    mutate(state.data);
    await renderPage();
    expectNoDisplay();
    expect(getStatus().getAttribute('role')).toBe('alert');
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expect(getRetry()).not.toBeNull();
    expectShell();
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(Object.keys(provenance))('requires root provenance %s', async (field) => {
    delete state.data[field];
    await renderPage();
    expectNoDisplay();
    expect(getStatus().getAttribute('role')).toBe('alert');
    expectShell();
  });
  it.each([
    ['synthetic', false], ['synthetic', 'true'], ['non_clinical', false], ['non_clinical', 1],
    ['clinically_reviewed', true], ['clinically_reviewed', 'false'],
    ['display_only', false], ['display_only', 'true'], ['numeric_semantics', 'risk'], ['numeric_semantics', null],
  ])('rejects non-exact root provenance %s=%j', async (field, value) => {
    state.data[field] = value;
    await renderPage();
    expectNoDisplay();
    expect(getStatus().textContent).toContain('los datos no son válidos');
  });
  it.each([null, [], 'invalid'])('rejects a malformed root envelope %j', async (data) => {
    state.data = data;
    await renderPage();
    expectNoDisplay();
    expect(getStatus().textContent).toContain('los datos no son válidos');
  });
});

const stateCases = [
  ['loading', { status: 'loading', loading: true, service: null }, 'Cargando datos', 'status'],
  ['loading status', { status: 'loading', loading: false }, 'Cargando datos', 'status'],
  ['no service', { status: 'empty', service: null }, 'No hay un servicio', 'status'],
  ['empty results', { status: 'empty' }, 'no tiene resultados', 'status'],
  ['permission', { status: 'permission', error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['unauthenticated', { status: 'permission', error: { status: 401 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', error: { kind: 'connection' } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', error: { kind: 'http', status: 500 } }, 'No fue posible cargar', 'alert'],
  ['invalid response', { status: 'error', error: { kind: 'invalid_data' } }, 'No fue posible cargar', 'alert'],
  ['unknown status', { status: 'unexpected' }, 'No fue posible cargar', 'alert'],
];
describe('accessible result states and preserved shell', () => {
  it('adds only page-scoped visible focus and wrapping for native demo controls and values', () => {
    expect(pageStyles).toMatch(/\.farmacogenetica-layout-new button:focus-visible\s*\{[^}]*outline:\s*3px solid #145f9f;[^}]*outline-offset:\s*3px;/);
    expect(pageStyles).toMatch(/\.farmacogenetica-layout-new \.farmaco-demo-values dd\s*\{[^}]*margin:\s*0;[^}]*overflow-wrap:\s*anywhere;/);
  });

  it.each(stateCases)('keeps neutral status copy and profile in %s while hiding stale display values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoDisplay();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    expect(getStatus().getAttribute('aria-busy')).toBe(String(override.status === 'loading'));
    expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(Boolean(getRetry())).toBe(override.status !== 'loading');
    if (override.status !== 'loading') expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(['no service', 'empty results', 'permission', 'connection error'])('uses the named native hook retry in %s', async (name) => {
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

  it('hides a previous display and disclaimer during retry before showing fresh hook data', async () => {
    state.data.disclaimer = 'Previous envelope disclosure.';
    await renderPage();
    state.retry.mockImplementation(() => { state = { ...state, status: 'loading', loading: true, data: null, service: null }; });
    await act(async () => getRetry().click());
    await renderPage();
    expectNoDisplay();
    expect(container.textContent).not.toContain('Previous envelope disclosure.');
    expectShell();
    state = makeState();
    state.data.results[0].payload.display.items[0].display_value = 12;
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe('12');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('distinguishes an empty raw results array from a missing module', async () => {
    state.data.results = [];
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados');
    expectNoDisplay();
    expectShell();
  });

  it.each([{ user: { name: 'Wrapped profile' } }, { name: 'Direct profile' }])('preserves independent ME response shape %j', async (data) => {
    state.status = 'permission';
    apiRequest.mockResolvedValue({ ok: true, data });
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain(data.user?.name || data.name);
  });

  it.each(['failed', 'rejected'])('does not let a %s ME request block the normalized demo', async (mode) => {
    if (mode === 'rejected') apiRequest.mockRejectedValueOnce(new Error('Profile unavailable'));
    else apiRequest.mockResolvedValueOnce({ ok: false, data: null });
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe('8');
    expect(getStatus().textContent).toContain('disponibles');
  });

  it('shows normalized results while the independent ME profile is still pending', async () => {
    apiRequest.mockImplementationOnce(() => new Promise(() => {}));
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe('8');
    expect(getStatus().textContent).toContain('disponibles');
    expectShell();
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps only retained dashboard navigation in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/rasgos', '/dashboard/farmacogenetica',
      '/dashboard/enfermedades',
    ]);
    await act(async () => container.querySelector('a[href="/dashboard/ancestria"]').click());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/ancestria');
  });

  it.each(['ready', 'loading', 'permission', 'error'])('preserves accessible mobile menu and desktop resize in %s', async (status) => {
    window.innerWidth = 768;
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    const burger = container.querySelector('button[aria-label="Abrir menú de navegación"]');
    expect(burger.type).toBe('button');
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    expect(burger.getAttribute('aria-controls')).toBe('farmaco-navigation');
    expect(document.getElementById('farmaco-navigation')).toBe(container.querySelector('aside.farmaco-sidebar-area'));
    expect(burger.querySelector('svg').getAttribute('aria-hidden')).toBe('true');
    await act(async () => burger.click());
    expect(burger.getAttribute('aria-label')).toBe('Cerrar menú de navegación');
    expect(burger.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector('nav').getAttribute('data-open')).toBe('true');
    await act(async () => [...container.querySelectorAll('nav button')].find((button) => button.textContent === 'Cerrar navegación').click());
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    await act(async () => burger.click());
    await act(async () => { window.innerWidth = 1440; window.dispatchEvent(new Event('resize')); });
    expect(container.querySelector('.farmaco-burger')).toBeNull();
    expect(container.querySelector('nav').getAttribute('data-open')).toBe('false');
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
      expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/farmacogenetica');
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
