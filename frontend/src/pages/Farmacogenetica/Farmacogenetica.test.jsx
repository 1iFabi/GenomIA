import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { AuthProvider } from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/ProtectedRoute';
import Farmacogenetica from './Farmacogenetica';

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
const makeGene = () => ({
  gene: 'CYP2C19', diplotype: '*1/*2', phenotype: 'Metabolizador intermedio',
  drugs: ['Clopidogrel', 'Omeprazol'], simulated: true,
});
const makeState = () => ({
  status: 'ready', loading: false, error: null, retry: vi.fn(),
  data: { disclaimer, sample_code: 'SEED-1', modules: { pharmacogenetics: [makeGene()] } },
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
const rowNames = () => [...container.querySelectorAll('.pgx-row')].map((row) => row.dataset.med);
const search = async (text) => {
  const input = container.querySelector('input[type="search"]');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  await act(async () => { set.call(input, text); input.dispatchEvent(new Event('input', { bubbles: true })); });
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
const expectNoDisplay = () => {
  expect(container.querySelector('dl')).toBeNull();
  expect(container.textContent).not.toContain('CYP2C19');
};
const expectShell = () => {
  expect(container.querySelector('main h1')).not.toBeNull();
  expect(container.querySelector('main.farmaco-main-content')).not.toBeNull();
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

describe('pharmacogenetics results', () => {
  it('lists every medication its genes decide in one table, grouped by what the guideline says', async () => {
    await renderPage();
    expectShell();
    expect(container.querySelector('main h1').textContent).toBe('Tus remedios');
    const names = rowNames();
    expect(names.slice(0, 1)).toEqual(['Clopidogrel']);
    expect(names).toContain('Omeprazol');
    // the nine CYP2C19 drugs; amitriptyline also needs CYP2D6, which this profile lacks
    expect(names).toHaveLength(9);
    expect([...container.querySelectorAll('.pgx-group th')].map((th) => th.textContent))
      .toEqual(['Conversar con tu médico', 'Habitual, con un matiz', 'Como la mayoría', 'No lo analizamos']);
    expect(container.querySelector('.pgx-row[data-med="Clopidogrel"]').textContent).toContain('Metabolizador intermedio');
    expect(container.textContent).not.toContain(disclaimer);
    expect(container.textContent).toContain('No cambies ni dejes un medicamento sin hablar con tu médico.');
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getRetry()).toBeUndefined();
  });

  it('opens a row in place with the sentence and the gene that decides it, never the dosing guideline', async () => {
    await renderPage();
    const toggle = container.querySelector('.pgx-row[data-med="Clopidogrel"] .pgx-row__name');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    await act(async () => toggle.click());
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const detail = document.getElementById(toggle.getAttribute('aria-controls'));
    expect(detail.querySelector('.pgx-detail__say').textContent).toContain('lo activa más despacio');
    expect(detail.querySelector('.pgx-detail__guide')).toBeNull();
    expect(detail.textContent).not.toContain('prasugrel o ticagrelor');
    expect(detail.querySelector('.pgx-gene h4').textContent).toBe('Tu CYP2C19 *1/*2');
    expect(detail.querySelector('[role="img"]').getAttribute('aria-label')).toContain('CYP2C19: Metabolizador intermedio');
    await act(async () => toggle.click());
    expect(container.querySelector('.pgx-detail')).toBeNull();
  });

  it('searches by name or use, and never lets an untested drug read as usual', async () => {
    await renderPage();
    await search('omeprazol');
    expect(rowNames()).toEqual(['Omeprazol']);
    await search('losec');
    expect(container.querySelector('.pgx-none')).not.toBeNull();
    await search('abacavir');
    expect(rowNames()).toEqual(['Abacavir']);
    expect(container.querySelector('.pgx-row').textContent).toContain('No lo analizamos');
    await search('paracetamol');
    expect(container.querySelector('.pgx-none').textContent).toContain('no cambian la indicación conocida');
  });

  it('filters the table from the partition bar and sorts by a column', async () => {
    await renderPage();
    const seg = (label) => [...container.querySelectorAll('.pgx-pbar__seg')].find((b) => b.textContent.includes(label));
    expect(seg('Conversar').textContent).toContain('1');
    await act(async () => seg('Como la mayoría').click());
    expect(seg('Como la mayoría').getAttribute('aria-pressed')).toBe('true');
    expect(rowNames()).not.toContain('Clopidogrel');
    await act(async () => seg('Como la mayoría').click());
    await act(async () => [...container.querySelectorAll('thead button')].find((b) => b.textContent === 'Remedio').click());
    const names = rowNames();
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, 'es')));
    expect(container.querySelector('.pgx-group')).toBeNull();
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

  it('reports a missing module when the service only has other results', async () => {
    state.data.modules = { traits: [{ trait: 'cafeina', label: 'Cafeína', result: 'Rápido' }] };
    await renderPage();
    expectNoDisplay();
    expect(getStatus().textContent).toContain('no tiene resultados de farmacogenética');
  });
});

const stateCases = [
  ['loading', { status: 'loading', loading: true, data: null }, 'Cargando datos', 'status'],
  ['empty', { status: 'empty', data: null }, 'Aún no tienes resultados', 'status'],
  ['permission', { status: 'permission', data: null, error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['unauthenticated', { status: 'permission', data: null, error: { status: 401 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', data: null, error: { kind: 'connection' } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', data: null, error: { kind: 'http', status: 500 } }, 'No fue posible cargar', 'alert'],
  ['invalid response', { status: 'error', data: null, error: { kind: 'invalid_data' } }, 'No fue posible cargar', 'alert'],
];
describe('accessible result states and preserved shell', () => {

  it.each(stateCases)('keeps neutral status copy and profile in %s while hiding stale display values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoDisplay();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    expect(getStatus().getAttribute('aria-busy')).toBe(String(override.status === 'loading'));
    if (override.status === 'loading') {
      // the page's own shape: the real title, the search and column words, eight rows waiting
      expect(container.querySelector('main h1').textContent).toBe('Tus remedios');
      expect(getStatus().querySelectorAll('.pgx-row--ghost')).toHaveLength(8);
      expect(getStatus().querySelector('.pgx-search').textContent).toBe('Buscar remedio');
      expect(getStatus().querySelector('[aria-hidden="true"]').contains(getStatus().querySelector('table'))).toBe(true);
    } else {
      expect(getStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    }
    expect(Boolean(getRetry())).toBe(override.status !== 'loading');
    if (override.status !== 'loading') expect(getRetry().getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(apiRequest.mock.calls.map(([url]) => url)).toEqual([API_ENDPOINTS.ME]);
  });

  it.each(['empty', 'permission', 'connection error'])('uses the named native hook retry in %s', async (name) => {
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
    // a refetch: the hook drops back to loading with no data
    state = { ...state, status: 'loading', loading: true, data: null, service: null };
    await renderPage();
    expectNoDisplay();
    expect(container.textContent).not.toContain('Previous envelope disclosure.');
    expectShell();
    state = makeState();
    state.data.modules.pharmacogenetics[0].phenotype = 'Metabolizador lento';
    await renderPage();
    await act(async () => container.querySelector('.pgx-row[data-med="Clopidogrel"]').click());
    expect(container.querySelector('.pgx-detail__say').textContent).toContain('casi no lo activa');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('treats an empty pharmacogenetics module as missing', async () => {
    state.data.modules = { pharmacogenetics: [] };
    await renderPage();
    expect(getStatus().textContent).toContain('no tiene resultados de farmacogenética');
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
    expect(rowNames()[0]).toBe('Clopidogrel');
    expect(getStatus().textContent).toContain('disponibles');
  });

  it('shows normalized results while the independent ME profile is still pending', async () => {
    apiRequest.mockImplementationOnce(() => new Promise(() => {}));
    await renderPage();
    expect(rowNames()[0]).toBe('Clopidogrel');
    expect(getStatus().textContent).toContain('disponibles');
    expectShell();
  });

  it.each(['ready', 'loading', 'permission', 'error'])('keeps only retained dashboard navigation in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toEqual([
      '/dashboard/ancestria', '/dashboard/farmacogenetica', '/dashboard/rasgos',
      '/dashboard/enfermedades#polygenic_risk', '/dashboard/enfermedades#monogenic_risk', '/dashboard/modulos',
    ]);
    await act(async () => container.querySelector('a[href="/dashboard/ancestria"]').click());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/ancestria');
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
