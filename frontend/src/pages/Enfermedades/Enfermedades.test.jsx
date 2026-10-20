import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { AuthProvider } from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/ProtectedRoute';
import Enfermedades from './Enfermedades';

vi.mock('../../hooks/useLatestGenomicsResults', async (importOriginal) => ({
  ...await importOriginal(), useLatestGenomicsResults: vi.fn(),
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
const makePolygenic = (percentile = 37.4) => ({
  condition: 'diabetes_tipo_2', label: 'Diabetes tipo 2', category: 'Promedio', percentile, score: 1.2,
  risk_loci: 12, simulated: true,
});
const makeState = () => ({
  status: 'ready', loading: false, error: null, retry: vi.fn(),
  data: {
    disclaimer, sample_code: 'SEED-1',
    modules: { polygenic_risk: [makePolygenic()] },
  },
});

let state;
let root;
let container;
let originalInnerWidth;
function LocationMarker() {
  return <output aria-label="Current route">{useLocation().pathname}</output>;
}
const renderPage = async ({ protectedRoute = false, entry = '/dashboard/enfermedades' } = {}) => {
  await act(async () => root.render(
    <MemoryRouter initialEntries={[entry]}>
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
const expectNoValues = () => expect(container.querySelector('.pgs-row')).toBeNull();
const placeOf = (row = 0) => getPanel('polygenic_risk').querySelectorAll('.pgs-row__place b')[row].textContent;
const expectShell = () => {
  expect(container.querySelector('h1').textContent).toBe('Frente al promedio');
  expect(container.querySelector('main.pgs-main-content')).not.toBeNull();
  expect(container.querySelector('nav[aria-label="Dashboard navigation"]')).not.toBeNull();
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

describe('risk results', () => {
  it('shows polygenic percentiles without the backend disclaimer', async () => {
    await renderPage();
    expectShell();
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getPanel('polygenic_risk').querySelector('.pgs-row__name').textContent).toBe('Diabetes tipo 2');
    expect(placeOf()).toBe('37');
    expect(container.textContent).not.toContain(disclaimer);
  });

  it('opens a condition into its place and what the number does not measure', async () => {
    state.data.modules.polygenic_risk = [makePolygenic(), { ...makePolygenic(91.2), condition: 'alzheimer', label: 'Enfermedad de Alzheimer' }];
    await renderPage();
    const heads = getPanel('polygenic_risk').querySelectorAll('.pgs-row__head');
    expect([...heads].map((head) => head.getAttribute('aria-expanded'))).toEqual(['true', 'false']);
    await act(async () => heads[1].click());
    expect([...heads].map((head) => head.getAttribute('aria-expanded'))).toEqual(['false', 'true']);
    const open = document.getElementById(heads[1].getAttribute('aria-controls'));
    expect(open.querySelector('.pgs-big b').textContent).toBe('91');
    expect(open.textContent).toContain('Lo que este número no mide');
    expect(open.textContent).toContain('no si vas a tener enfermedad de alzheimer');
    expect(open.textContent).toContain('Se sumaron 12 variantes');
    await act(async () => heads[1].click());
    expect(getPanel('polygenic_risk').querySelector('.pgs-halves')).toBeNull();
  });

  it('reuses the StrictMode guard profile and retains it after the result page remounts', async () => {
    await renderPage({ protectedRoute: true });
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.ME, { method: 'GET' });
  });

  it('opens straight on the polygenic section linked from its dashboard card', async () => {
    const scrolled = [];
    Element.prototype.scrollIntoView = vi.fn(function scrollIntoView() { scrolled.push(this.id); });
    await renderPage({ entry: '/dashboard/enfermedades#polygenic_risk' });
    expect(getPanel('polygenic_risk').id).toBe('polygenic_risk');
    expect(scrolled).toEqual(['polygenic_risk']);
    delete Element.prototype.scrollIntoView;
  });

  it('opens the monogenic page on its own hash', async () => {
    Element.prototype.scrollIntoView = vi.fn();
    await renderPage({ entry: '/dashboard/enfermedades#monogenic_risk' });
    expect(container.querySelector('main.mono-main-content')).not.toBeNull();
    expect(container.querySelector('main h1').textContent).toBe('Gen por gen');
    expect(getPanel('polygenic_risk')).toBeNull();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    delete Element.prototype.scrollIntoView;
  });

  it('stays at the top when no section is linked', async () => {
    Element.prototype.scrollIntoView = vi.fn();
    await renderPage();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    delete Element.prototype.scrollIntoView;
  });

  it('never requests the legacy disease endpoint', async () => {
    await renderPage();
    expect(useLatestGenomicsResults).toHaveBeenCalled();
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it('reports missing risk modules when the service only has other results', async () => {
    state.data.modules = { traits: [{ trait: 'cafeina', label: 'Cafeína', result: 'Rápido' }] };
    await renderPage();
    expectNoValues();
    expect(getStatus().textContent).toContain('no tiene resultados de riesgo');
  });
});

const stateCases = [
  ['loading', { status: 'loading', loading: true, data: null }, 'Cargando datos', 'status'],
  ['empty', { status: 'empty', data: null }, 'Aún no tienes resultados', 'status'],
  ['permission', { status: 'permission', data: null, error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', data: null, error: { kind: 'connection', status: 0 } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', data: null, error: { kind: 'http', status: 500 } }, 'No fue posible cargar', 'alert'],
  ['invalid response error', { status: 'error', data: null, error: { kind: 'invalid_data' } }, 'No fue posible cargar', 'alert'],
];
describe('result states and independent page shell', () => {

  it.each(stateCases)('keeps neutral status copy, shell and profile in %s without stale values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoValues();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    expect(getStatus().getAttribute('aria-busy')).toBe(String(state.loading));
    if (state.loading) {
      expect(getStatus().querySelectorAll('.pgs-skel-row')).toHaveLength(5);
      expect(getStatus().querySelector('.pgs-sheet').getAttribute('aria-hidden')).toBe('true');
    } else {
      expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    }
    expect(Boolean(getRetry())).toBe(!state.loading);
    if (!state.loading) expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(container.textContent).not.toMatch(/predisposición|sin riesgo|no se encontraron/i);
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(['empty', 'permission', 'connection error'])('uses the named hook retry in %s', async (name) => {
    Object.assign(state, stateCases.find(([key]) => key === name)[1]);
    await renderPage();
    await act(async () => getRetry().click());
    expect(state.retry).toHaveBeenCalledTimes(1);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('clears old display values during retry and renders only the next normalized response', async () => {
    await renderPage();
    // a ready page has no retry button; the hook's retry is what moves it back to loading
    state = { ...state, status: 'loading', loading: true, data: null, service: null };
    await renderPage();
    expectNoValues();
    expectShell();
    expect(getStatus().textContent).toContain('Cargando datos');
    state = makeState();
    state.data.modules.polygenic_risk = [makePolygenic(81.6)];
    await renderPage();
    expect(placeOf()).toBe('82');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('treats empty risk modules as missing', async () => {
    state.data.modules = { polygenic_risk: [], monogenic_risk: [] };
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados de riesgo');
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
    expect(placeOf()).toBe('37');
    expect(getStatus().textContent).toContain('disponibles');
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps only retained navigation links in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/farmacogenetica', '/dashboard/rasgos',
      '/dashboard/enfermedades#polygenic_risk', '/dashboard/enfermedades#monogenic_risk', '/dashboard/modulos',
    ]);
    await act(async () => container.querySelector('a[href="/dashboard/rasgos"]').click());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/rasgos');
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
