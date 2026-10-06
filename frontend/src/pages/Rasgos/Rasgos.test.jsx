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
import Rasgos from './Rasgos';

const pageStyles = readFileSync(resolve(cwd(), 'src/pages/Rasgos/Rasgos.css'), 'utf8');

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

const provenance = {
  synthetic: true, non_clinical: true, clinically_reviewed: false, display_only: true,
  numeric_semantics: 'arbitrary_demo_only_not_evaluated',
  disclaimer: 'Synthetic, non-clinical, display-only demonstration.',
};
const makeModule = (module = 'traits', kind = 'demo_traits', value = 24) => ({
  module, result_type: 'synthetic_placeholder', value_code: 'SYNTHETIC_NOT_EVALUATED',
  payload: {
    ...provenance, module, label: 'Demo trait A', state: 'not_evaluated',
    display: { kind, items: [{ label: 'Demo trait A', display_value: value }] },
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
  const copy = container.querySelector('main');
  const accessibleCopy = [...copy.querySelectorAll('[aria-label], [aria-description], [aria-valuetext], [title], [alt]')]
    .flatMap((node) => ['aria-label', 'aria-description', 'aria-valuetext', 'title', 'alt']
      .map((attribute) => node.getAttribute(attribute) || '')).join(' ');
  expect(`${copy.textContent} ${accessibleCopy}`).not.toMatch(
    /demo|demostraci[oó]n|sint[eé]tic[oa]s?|synthetic|no[\s_-]+evaluad[oa]s?|not[\s_-]+evaluated|no cl[ií]nic[oa]s?|non[\s_-]+clinical|sin revisi[oó]n cl[ií]nica|arbitrari[oa]s?/i
  );
};
const expectNoValues = () => expect(container.querySelector('dd')).toBeNull();
const expectShell = () => {
  expect(container.querySelector('h1')).not.toBeNull();
  expect(container.querySelector('h1').textContent).toBe('Rasgos');
  expect(container.querySelector('main.rasgos-layout__main')).not.toBeNull();
  expect(container.querySelector('aside.rasgos-layout__sidebar nav')).not.toBeNull();
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

describe('normalized traits results', () => {
  it('renders the localized category and raw value without visible or accessible disclosure copy', async () => {
    const rawData = structuredClone(state.data);
    await renderPage();
    expectShell();
    expect(container.querySelector('dt').textContent).toBe('Rasgo A');
    expect(state.data).toEqual(rawData);
    expect(container.querySelector('dd').textContent).toBe('24');
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.textContent).not.toMatch(/%|predisposición|magnitud|genotipo|fenotipo|diagnóstico|predicción|promedio/i);
    expect(getStatus().textContent).toContain('disponibles');
    expect(getRetry()).not.toBeNull();
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

  it.each([0, -7.25, 137, 0.001, 1e100])('preserves raw finite value %s without units, clamping or rounding', async (value) => {
    state.data.results[0].payload.display.items[0].display_value = value;
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe(String(value));
    expect(container.textContent).not.toMatch(/%|riesgo|puntaje|score|probabilidad|predicción|diagnóstico|tratamiento/i);
    expect(container.querySelector('[role="img"]')).toBeNull();
  });

  it('neutralizes label prefixes and localizes alternate categories without exposing biological fields', async () => {
    const payload = state.data.results[0].payload;
    Object.assign(payload, {
      name: 'Legacy trait', fenotipo: 'Legacy phenotype', genotipo: 'AA', rsid: 'rs123',
      nivel_riesgo: 'Alto', magnitud_efecto: 99, description: 'Legacy advice', group: 'Bienestar y Salud',
    });
    Object.assign(payload.display.items[0], { label: '  Demo label retained  ', unit: '%', interpretation: 'Legacy prediction' });
    payload.display.items.push({ label: 'Demo trait B', display_value: 6.75 });
    await renderPage();
    expect([...container.querySelectorAll('dt')].map((item) => item.textContent)).toEqual(['  label retained  ', 'Rasgo B']);
    expect([...container.querySelectorAll('dd')].map((item) => item.textContent)).toEqual(['24', '6.75']);
    expect(payload.display.items.map((item) => item.label)).toEqual(['  Demo label retained  ', 'Demo trait B']);
    expectNeutralCopy();
    expect(container.textContent).not.toMatch(/Legacy|AA|rs123|99|Alto|Bienestar|%/);
  });

  it.each(['Etiqueta conservada', '  Etiqueta conservada  '])('preserves other usable display labels exactly: %s', async (label) => {
    state.data.results[0].payload.display.items[0].label = label;
    await renderPage();
    expect(container.querySelector('dt').textContent).toBe(label);
    expect(container.querySelector('dd').textContent).toBe('24');
    expectNeutralCopy();
  });

  it('does not manufacture a display from a v1 release version', async () => {
    state.service.release_version = '1';
    delete state.data.results[0].payload.display;
    state.data.results[0].payload.rows = [{ label: 'Demo trait A', state: 'not_evaluated', value: null }];
    await renderPage();
    expectNoValues();
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expectShell();
  });

  it('does not borrow a value when the traits module is missing', async () => {
    state.data.results = ['global_ancestry', 'local_ancestry', 'polygenic_risk', 'monogenic_risk', 'pharmacogenetics']
      .map((module) => makeModule(module, 'demo_traits', 99));
    await renderPage();
    expectNoValues();
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getStatus().textContent).toContain('El módulo de rasgos no está disponible');
    expect(container.textContent).not.toMatch(/Demo trait A|99/);
    expectShell();
  });

  it('ignores displays in the other known modules when traits is present', async () => {
    state.data.results.push(...['global_ancestry', 'local_ancestry', 'polygenic_risk', 'monogenic_risk', 'pharmacogenetics']
      .map((module) => ({ module, payload: { display: { kind: 'other', items: [{ label: 'Other module', display_value: 99 }] } } })));
    await renderPage();
    expect(container.querySelectorAll('dd')).toHaveLength(1);
    expect(container.querySelector('dd').textContent).toBe('24');
    expect(container.textContent).not.toMatch(/Other module|99/);
  });

  const invalidModules = [
    ['duplicate traits module', (result, data) => data.results.push(structuredClone(result))],
    ['unexpected module ID', (result) => { result.module = 'unexpected_traits'; }],
    ['missing payload', (result) => { delete result.payload; }],
    ['null payload', (result) => { result.payload = null; }],
    ['array payload', (result) => { result.payload = []; }],
    ['mismatched payload module', (result) => { result.payload.module = 'polygenic_risk'; }],
    ['missing state', (result) => { delete result.payload.state; }],
    ['evaluated state', (result) => { result.payload.state = 'evaluated'; }],
    ['unexpected result type', (result) => { result.result_type = 'clinical'; }],
    ['missing value code', (result) => { delete result.value_code; }],
    ['non-synthetic payload', (result) => { result.payload.synthetic = false; }],
    ['missing non-clinical payload', (result) => { delete result.payload.non_clinical; }],
    ['clinically reviewed payload', (result) => { result.payload.clinically_reviewed = true; }],
    ['missing review provenance', (result) => { delete result.payload.clinically_reviewed; }],
    ['non-display-only payload', (result) => { result.payload.display_only = false; }],
    ['missing numeric semantics', (result) => { delete result.payload.numeric_semantics; }],
    ['clinical numeric semantics', (result) => { result.payload.numeric_semantics = 'probability'; }],
    ['missing disclaimer', (result) => { delete result.payload.disclaimer; }],
    ['blank disclaimer', (result) => { result.payload.disclaimer = '  '; }],
    ['missing module label', (result) => { delete result.payload.label; }],
    ['blank module label', (result) => { result.payload.label = '  '; }],
    ['missing display', (result) => { delete result.payload.display; }],
    ['null display', (result) => { result.payload.display = null; }],
    ['array display', (result) => { result.payload.display = []; }],
    ['unexpected display kind', (result) => { result.payload.display.kind = 'probability'; }],
    ['other demo display kind', (result) => { result.payload.display.kind = 'demo_entries'; }],
    ['missing items', (result) => { delete result.payload.display.items; }],
    ['non-array items', (result) => { result.payload.display.items = {}; }],
    ['empty items', (result) => { result.payload.display.items = []; }],
    ['null item', (result) => { result.payload.display.items = [null]; }],
    ['array item', (result) => { result.payload.display.items = [[]]; }],
    ['missing item label', (result) => { delete result.payload.display.items[0].label; }],
    ['blank item label', (result) => { result.payload.display.items[0].label = '  '; }],
    ['non-text item label', (result) => { result.payload.display.items[0].label = 24; }],
    ['duplicate item label', (result) => { result.payload.display.items.push({ ...result.payload.display.items[0] }); }],
    ['missing value', (result) => { delete result.payload.display.items[0].display_value; }],
    ...[NaN, Infinity, -Infinity, '24', null, true, {}].map((value) => [
      `non-finite or non-numeric value ${String(value)}`,
      (result) => { result.payload.display.items[0].display_value = value; },
    ]),
    ['malformed second item', (result) => { result.payload.display.items.push({ label: 'Demo trait B', display_value: NaN }); }],
  ];
  it.each(invalidModules)('rejects %s without partial values or fallback', async (_name, mutate) => {
    mutate(state.data.results[0], state.data);
    await renderPage();
    expectNoValues();
    expect(getStatus().getAttribute('role')).toBe('alert');
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expect(getRetry()).not.toBeNull();
    expectShell();
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(Object.keys(provenance).filter((field) => field !== 'disclaimer'))('requires root provenance %s', async (field) => {
    delete state.data[field];
    await renderPage();
    expectNoValues();
    expect(getStatus().getAttribute('role')).toBe('alert');
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expectShell();
  });

  it.each([
    ['synthetic', false], ['synthetic', 'true'], ['non_clinical', false], ['non_clinical', 1],
    ['clinically_reviewed', true], ['clinically_reviewed', 'false'],
    ['display_only', false], ['display_only', 'true'], ['numeric_semantics', 'risk'], ['numeric_semantics', null],
  ])('requires exact root provenance %s=%j', async (field, value) => {
    state.data[field] = value;
    await renderPage();
    expectNoValues();
    expect(getStatus().getAttribute('role')).toBe('alert');
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expectShell();
  });

  it.each([
    ['missing envelope', () => { state.data = null; }],
    ['non-object envelope', () => { state.data = []; }],
    ['missing results', () => { delete state.data.results; }],
    ['non-array results', () => { state.data.results = {}; }],
    ['malformed result', () => { state.data.results.push(null); }],
    ['missing module ID', () => { state.data.results.push({ payload: {} }); }],
    ['non-text module ID', () => { state.data.results[0].module = 1; }],
    ['duplicate other module', () => { state.data.results.push({ module: 'global_ancestry' }, { module: 'global_ancestry' }); }],
    ['unexpected other module', () => { state.data.results.push({ module: 'unknown' }); }],
    ['missing root disclaimer', () => { delete state.data.disclaimer; }],
    ['blank root disclaimer', () => { state.data.disclaimer = ' '; }],
  ])('rejects %s', async (_name, mutate) => {
    mutate();
    await renderPage();
    expectNoValues();
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expectShell();
  });
});

const stateCases = [
  ['loading', { status: 'loading', loading: true, service: null }, 'Cargando datos', 'status'],
  ['loading status', { status: 'loading', loading: false }, 'Cargando datos', 'status'],
  ['no service', { status: 'empty', service: null }, 'No hay un servicio', 'status'],
  ['ready without service', { status: 'ready', service: null }, 'No hay un servicio', 'status'],
  ['empty results', { status: 'empty' }, 'no tiene resultados', 'status'],
  ['permission', { status: 'permission', error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['unauthenticated', { status: 'permission', error: { status: 401 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', error: { kind: 'connection', status: 0 } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', error: { kind: 'http', status: 404 } }, 'No fue posible cargar', 'alert'],
  ['invalid response error', { status: 'error', error: { kind: 'invalid_data' } }, 'No fue posible cargar', 'alert'],
  ['unknown state', { status: 'unexpected' }, 'No fue posible cargar', 'alert'],
];
describe('result states and preserved independent shell', () => {
  it('reuses page-scoped visible focus for the menu and native retry', () => {
    expect(pageStyles).toMatch(/\.rasgos-layout button:focus-visible\s*\{[^}]*outline:\s*3px solid #145f9f;[^}]*outline-offset:\s*3px;/);
  });

  it('keeps raw definition terms and values aligned and wrappable on narrow screens', () => {
    expect(/\.rasgos-page \.rasgos-field dt\s*,\s*\.rasgos-page \.rasgos-field dd\s*\{[^}]*margin:\s*0;[^}]*overflow-wrap:\s*anywhere;/.test(pageStyles)).toBe(true);
  });

  it.each(stateCases)('keeps neutral status copy and ME profile in %s without stale values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoValues();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    const loading = override.status === 'loading';
    expect(getStatus().getAttribute('aria-busy')).toBe(String(loading));
    expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(Boolean(getRetry())).toBe(!loading);
    if (!loading) expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(container.textContent).not.toMatch(/predisposición|sin riesgo|no se encontraron|no tienes rasgos/i);
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(['no service', 'empty results', 'permission', 'connection error'])('uses only the named hook retry in %s', async (name) => {
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

  it('clears the old display during retry and shows only the next normalized values', async () => {
    await renderPage();
    const retry = state.retry;
    retry.mockImplementation(() => { state = { ...state, status: 'loading', loading: true, data: null, service: null }; });
    await act(async () => getRetry().click());
    await renderPage();
    expectNoValues();
    expectShell();
    expect(getStatus().textContent).toContain('Cargando datos');
    state = makeState();
    state.data.results[0].payload.display.items[0].display_value = 8;
    await renderPage();
    expect(container.querySelector('dd').textContent).toBe('8');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('distinguishes an empty result array from a missing traits module', async () => {
    state.data.results = [];
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados');
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
    expect(container.querySelector('dd').textContent).toBe('24');
    expect(getStatus().textContent).toContain('disponibles');
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps only retained navigation links in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/rasgos', '/dashboard/farmacogenetica',
      '/dashboard/enfermedades',
    ]);
    await act(async () => container.querySelector('a[href="/dashboard/ancestria"]').click());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/ancestria');
    expectShell();
  });

  it.each(['ready', 'loading', 'permission', 'error'])('preserves the mobile menu and resize behavior in %s', async (status) => {
    window.innerWidth = 768;
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    const burger = container.querySelector('button[aria-label="Abrir menú de navegación"]');
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    expect(burger.querySelector('svg').getAttribute('aria-hidden')).toBe('true');
    await act(async () => burger.click());
    expect(burger.getAttribute('aria-label')).toBe('Cerrar menú de navegación');
    expect(burger.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector('nav').getAttribute('data-open')).toBe('true');
    await act(async () => [...container.querySelectorAll('nav button')].find((button) => button.textContent === 'Cerrar navegación').click());
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    await act(async () => burger.click());
    await act(async () => window.dispatchEvent(new Event('resize')));
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    await act(async () => { window.innerWidth = 1440; window.dispatchEvent(new Event('resize')); });
    expect(container.querySelector('.rasgos-layout__burger')).toBeNull();
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
