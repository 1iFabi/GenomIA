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
import Enfermedades from './Enfermedades';
const pageStyles = readFileSync(resolve(cwd(), 'src/pages/Enfermedades/Enfermedades.css'), 'utf8');

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
vi.mock('echarts-for-react', () => ({ default: () => <div>Legacy chart</div> }));
vi.mock('../../components/CircularProgress/CircularProgress', () => ({
  default: () => <div>Legacy score</div>,
}));
vi.mock('../../components/GlossaryCarousel/GlossaryCarousel', () => ({
  default: () => <div>Legacy glossary</div>,
}));
vi.mock('../../components/PriorityCard/PriorityCard', () => ({
  default: () => <div>Legacy priority</div>,
}));

const disclosure = {
  synthetic: true, non_clinical: true, disclaimer: 'Synthetic, non-clinical, display-only demonstration.',
};
const makeModule = (module, kind, value) => ({
  module, result_type: 'synthetic_placeholder', value_code: 'SYNTHETIC_NOT_EVALUATED',
  payload: {
    ...disclosure, module, label: 'Demo index A', state: 'not_evaluated',
    clinically_reviewed: false, display_only: true,
    numeric_semantics: 'arbitrary_demo_only_not_evaluated',
    display: { kind, items: [{ label: 'Demo index A', display_value: value }] },
  },
});
const makeState = () => ({
  status: 'ready', loading: false, service: { service_request_id: 'latest' }, error: null,
  data: {
    ...disclosure,
    clinically_reviewed: false, display_only: true,
    numeric_semantics: 'arbitrary_demo_only_not_evaluated',
    results: [makeModule('polygenic_risk', 'demo_index', 37), makeModule('monogenic_risk', 'demo_entries', 12)],
  },
  retry: vi.fn(),
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
    <MemoryRouter initialEntries={['/dashboard/enfermedades']}>
      <AuthProvider>
        {protectedRoute ? (
          <React.StrictMode><ProtectedRoute><Enfermedades /></ProtectedRoute></React.StrictMode>
        ) : <Enfermedades />}
        <LocationMarker />
      </AuthProvider>
    </MemoryRouter>
  ));
};
const getPanel = (module) => container.querySelector(`[aria-labelledby="${module}-title"]`);
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
  expect(container.querySelector('h1').textContent).toBe('ENFERMEDADES');
  expect(container.querySelector('main.enfermedades-layout__main')).not.toBeNull();
  expect(container.querySelector('aside.enfermedades-layout__sidebar nav')).not.toBeNull();
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

describe('normalized risk-module results', () => {
  it('renders localized categories and raw values without visible or accessible disclosure copy', async () => {
    const rawData = structuredClone(state.data);
    await renderPage();
    expectShell();
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    for (const [module, value] of [['polygenic_risk', '37'], ['monogenic_risk', '12']]) {
      const panel = getPanel(module);
      expect(panel).not.toBeNull();
      expect(panel.querySelector('dt').textContent).toBe('Índice A');
      expect(panel.querySelector('dd').textContent).toBe(value);
    }
    expect(state.data).toEqual(rawData);
    expect(container.textContent).not.toMatch(/%|Legacy|predisposición|prioridad|probabilidad/i);
  });

  it('reuses the StrictMode guard profile and retains it after the result page remounts', async () => {
    await renderPage({ protectedRoute: true });
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.ME, { method: 'GET' });
  });

  it('never requests the legacy disease endpoint', async () => {
    await renderPage();
    expect(useLatestGenomicsResults).toHaveBeenCalled();
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each([0, -7.25, 137, 0.001])('preserves the raw number %s without clamping, rounding or units', async (value) => {
    for (const result of state.data.results) result.payload.display.items[0].display_value = value;
    await renderPage();
    for (const module of ['polygenic_risk', 'monogenic_risk']) {
      expect(getPanel(module).querySelector('dd').textContent).toBe(String(value));
    }
    expect(container.textContent).not.toMatch(/%|riesgo|puntaje|score|probabilidad|predicción|diagnóstico|tratamiento/i);
  });

  it('localizes alternate categories but never renders legacy biological fields or service-version-derived values', async () => {
    state.service.release_version = '1';
    state.data.results[1].payload.display.items.push({ label: 'Demo index B', display_value: 6.75 });
    Object.assign(state.data.results[0].payload, {
      disease: 'Legacy disease', genotype: 'AA', rsid: 'rs123', chromosome: 'chr1', frequency: 99,
    });
    await renderPage();
    expect([...getPanel('monogenic_risk').querySelectorAll('dt')].map((item) => item.textContent)).toEqual(['Índice A', 'Índice B']);
    expect([...getPanel('monogenic_risk').querySelectorAll('dd')].map((item) => item.textContent)).toEqual(['12', '6.75']);
    expect(state.data.results[1].payload.display.items.map((item) => item.label)).toEqual(['Demo index A', 'Demo index B']);
    expect(container.textContent).not.toMatch(/Legacy disease|AA|rs123|chr1|99/);
    expectNeutralCopy();
  });

  it('does not borrow values from the other normalized modules', async () => {
    state.data.results = ['global_ancestry', 'local_ancestry', 'traits', 'pharmacogenetics']
      .map((module) => makeModule(module, 'demo_index', 99));
    await renderPage();
    expect(getStatus().textContent).toContain('Faltan módulos');
    expectNoValues();
    expect(getPanel('polygenic_risk').textContent).toContain('no disponible');
    expect(getPanel('monogenic_risk').textContent).toContain('no disponible');
  });

  it('accepts the other known module IDs without rendering their displays', async () => {
    state.data.results.push(...['global_ancestry', 'local_ancestry', 'traits', 'pharmacogenetics']
      .map((module) => ({ module, payload: { display: { kind: 'other', items: [{ label: 'Other module', display_value: 99 }] } } })));
    await renderPage();
    expect([...container.querySelectorAll('dd')].map((item) => item.textContent)).toEqual(['37', '12']);
    expect(container.textContent).not.toMatch(/Other module|99/);
  });

  describe.each(['polygenic_risk', 'monogenic_risk'])('%s validation', (module) => {
    it('marks a missing module unavailable without fabricating its value', async () => {
      state.data.results = state.data.results.filter((result) => result.module !== module);
      await renderPage();
      expect(getStatus().textContent).toContain('Faltan módulos');
      expect(getPanel(module).textContent).toContain('no disponible');
      expect(getPanel(module).querySelector('dd')).toBeNull();
      expect(container.querySelectorAll('dd')).toHaveLength(1);
      expectShell();
    });

    const invalidModules = [
      ['duplicate module', (result, data) => data.results.push(structuredClone(result))],
      ['unexpected module ID', (result) => { result.module = 'unexpected_risk'; }],
      ['missing payload', (result) => { delete result.payload; }],
      ['array payload', (result) => { result.payload = []; }],
      ['mismatched payload module', (result) => { result.payload.module = 'traits'; }],
      ['missing state', (result) => { delete result.payload.state; }],
      ['evaluated state', (result) => { result.payload.state = 'evaluated'; }],
      ['unexpected result type', (result) => { result.result_type = 'clinical'; }],
      ['missing value code', (result) => { delete result.value_code; }],
      ['non-synthetic provenance', (result) => { result.payload.synthetic = false; }],
      ['missing non-clinical provenance', (result) => { delete result.payload.non_clinical; }],
      ['clinically reviewed provenance', (result) => { result.payload.clinically_reviewed = true; }],
      ['missing review provenance', (result) => { delete result.payload.clinically_reviewed; }],
      ['non-display-only provenance', (result) => { result.payload.display_only = false; }],
      ['missing numeric semantics', (result) => { delete result.payload.numeric_semantics; }],
      ['clinical numeric semantics', (result) => { result.payload.numeric_semantics = 'probability'; }],
      ['missing disclaimer', (result) => { delete result.payload.disclaimer; }],
      ['blank disclaimer', (result) => { result.payload.disclaimer = '  '; }],
      ['non-text disclaimer', (result) => { result.payload.disclaimer = {}; }],
      ['missing module label', (result) => { delete result.payload.label; }],
      ['clinical module label', (result) => { result.payload.label = 'Disease'; }],
      ['v1 placeholder without display', (result) => {
        delete result.payload.display;
        result.payload.rows = [{ label: 'Synthetic placeholder', state: 'not_evaluated', value: null }];
      }],
      ['null display', (result) => { result.payload.display = null; }],
      ['unexpected display kind', (result) => { result.payload.display.kind = 'probability'; }],
      ['other target display kind', (result) => {
        result.payload.display.kind = module === 'polygenic_risk' ? 'demo_entries' : 'demo_index';
      }],
      ['missing items', (result) => { delete result.payload.display.items; }],
      ['non-array items', (result) => { result.payload.display.items = {}; }],
      ['empty items', (result) => { result.payload.display.items = []; }],
      ['null item', (result) => { result.payload.display.items = [null]; }],
      ['missing item label', (result) => { delete result.payload.display.items[0].label; }],
      ['blank item label', (result) => { result.payload.display.items[0].label = '  '; }],
      ['non-text item label', (result) => { result.payload.display.items[0].label = 37; }],
      ['clinical item label', (result) => { result.payload.display.items[0].label = 'Disease'; }],
      ['localized input label', (result) => { result.payload.display.items[0].label = 'Índice A'; }],
      ['duplicate item label', (result) => { result.payload.display.items.push({ ...result.payload.display.items[0] }); }],
      ['missing value', (result) => { delete result.payload.display.items[0].display_value; }],
      ...[NaN, Infinity, -Infinity, '37', null, true].map((value) => [
        `non-finite or non-numeric value ${String(value)}`,
        (result) => { result.payload.display.items[0].display_value = value; },
      ]),
      ['malformed second item', (result) => { result.payload.display.items.push({ label: 'Demo index B', display_value: NaN }); }],
    ];
    it.each(invalidModules)('rejects %s without partial displays or fallback', async (_name, mutate) => {
      mutate(state.data.results.find((result) => result.module === module), state.data);
      await renderPage();
      expectNoValues();
      expect(getStatus().getAttribute('role')).toBe('alert');
      expect(getStatus().textContent).toContain('los datos no son válidos');
      expect(getRetry()).not.toBeNull();
      expectShell();
      expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
    });
  });

  it.each([
    'synthetic', 'non_clinical', 'clinically_reviewed', 'display_only', 'numeric_semantics',
  ])('rejects an omitted required root provenance field: %s', async (field) => {
    delete state.data[field];
    await renderPage();
    expectNoValues();
    expect(getStatus().getAttribute('role')).toBe('alert');
    expect(getStatus().textContent).toContain('los datos no son válidos');
    expect(getRetry()).not.toBeNull();
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
    ['duplicate non-target module', () => { state.data.results.push({ module: 'traits' }, { module: 'traits' }); }],
    ['non-synthetic envelope', () => { state.data.synthetic = false; }],
    ['missing non-clinical envelope', () => { delete state.data.non_clinical; }],
    ['blank envelope disclaimer', () => { state.data.disclaimer = ' '; }],
    ['conflicting envelope review', () => { state.data.clinically_reviewed = true; }],
    ['conflicting envelope display-only', () => { state.data.display_only = false; }],
    ['conflicting envelope numeric semantics', () => { state.data.numeric_semantics = 'risk'; }],
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
  ['no service', { status: 'empty', service: null }, 'No hay un servicio', 'status'],
  ['empty results', { status: 'empty' }, 'no tiene resultados', 'status'],
  ['permission', { status: 'permission', error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', error: { kind: 'connection', status: 0 } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', error: { kind: 'http', status: 404 } }, 'No fue posible cargar', 'alert'],
  ['invalid response error', { status: 'error', error: { kind: 'invalid_data' } }, 'No fue posible cargar', 'alert'],
  ['unknown state', { status: 'unexpected' }, 'No fue posible cargar', 'alert'],
];
describe('result states and independent page shell', () => {
  it('provides page-scoped visible keyboard focus for the menu and retry', () => {
    expect(pageStyles).toMatch(/\.enfermedades-layout__burger:focus-visible\s*,\s*\.enfermedades-page button:focus-visible\s*\{[^}]*outline:\s*3px solid #0b7ad0;[^}]*outline-offset:\s*4px;/);
  });

  it.each(stateCases)('keeps neutral status copy, shell and profile in %s without stale values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoValues();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    expect(getStatus().getAttribute('aria-busy')).toBe(String(state.loading));
    expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(Boolean(getRetry())).toBe(!state.loading);
    if (!state.loading) expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(container.textContent).not.toMatch(/predisposición|sin riesgo|no se encontraron/i);
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(['no service', 'empty results', 'permission', 'connection error'])('uses the named hook retry in %s', async (name) => {
    Object.assign(state, stateCases.find(([key]) => key === name)[1]);
    await renderPage();
    await act(async () => getRetry().click());
    expect(state.retry).toHaveBeenCalledTimes(1);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('clears old display values during retry and renders only the next normalized response', async () => {
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
    expect(getPanel('polygenic_risk').querySelector('dd').textContent).toBe('8');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('distinguishes an actually empty result array from a missing module', async () => {
    state.data.results = [];
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados');
    expectNoValues();
    expectShell();
  });

  it.each([{ user: { name: 'Wrapped profile' } }, { name: 'Direct profile' }])('preserves the supported ME response shape %j', async (data) => {
    state.status = 'permission';
    apiRequest.mockResolvedValue({ ok: true, data });
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain(data.user?.name || data.name);
    expect(getStatus().textContent).toContain('No tienes permiso');
  });

  it('does not turn a failed ME response into a result failure', async () => {
    apiRequest.mockResolvedValue({ ok: false, data: null });
    await renderPage();
    expect(getPanel('polygenic_risk').querySelector('dd').textContent).toBe('37');
    expect(getStatus().textContent).toContain('disponibles');
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps only retained navigation links in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/rasgos', '/dashboard/farmacogenetica',
      '/dashboard/enfermedades',
    ]);
    await act(async () => container.querySelector('a[href="/dashboard/rasgos"]').click());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/rasgos');
    expectShell();
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps the mobile menu working in %s', async (status) => {
    window.innerWidth = 768;
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    const burger = container.querySelector('button[aria-label="Abrir menú"]');
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    expect(burger.querySelector('svg').getAttribute('aria-hidden')).toBe('true');
    await act(async () => burger.click());
    expect(burger.getAttribute('aria-label')).toBe('Cerrar menú');
    expect(burger.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector('nav').getAttribute('data-open')).toBe('true');
    await act(async () => [...container.querySelectorAll('nav button')].find((button) => button.textContent === 'Cerrar navegación').click());
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    await act(async () => burger.click());
    await act(async () => { window.innerWidth = 1440; window.dispatchEvent(new Event('resize')); });
    expect(container.querySelector('.enfermedades-layout__burger')).toBeNull();
    expect(container.querySelector('nav').getAttribute('data-open')).toBe('false');
    expectShell();
  });

  it.each(['ready', 'loading', 'permission', 'error'])('clears the session and navigates home on logout in %s', async (status) => {
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
      expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/enfermedades');
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
