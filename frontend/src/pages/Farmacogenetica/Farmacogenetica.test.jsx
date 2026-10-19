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
  it('shows each medication with a plain sentence and its speed rule, and the backend disclaimer', async () => {
    await renderPage();
    expectShell();
    expect(container.querySelector('main h1').textContent).toBe('Tus remedios');
    const cards = [...container.querySelectorAll('.pgx-card')];
    expect(cards.map((c) => c.querySelector('.pgx-card__name').textContent)).toEqual(['Clopidogrel', 'Omeprazol']);
    expect(cards[0].querySelector('.pgx-card__say').textContent).toContain('activa el clopidogrel más despacio');
    expect(cards[0].querySelector('[role="img"]').getAttribute('aria-label')).toContain('CYP2C19: Metabolizador intermedio');
    expect(container.querySelector('#pgx-talk').textContent).toBe('Para conversar con tu médico');
    expect(container.textContent).toContain(disclaimer);
    expect(container.textContent).toContain('No cambies ni dejes un medicamento sin hablar con tu médico.');
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(getStatus().getAttribute('role')).toBe('status');
    expect(getRetry()).toBeUndefined();
  });

  it('opens a medication into the page with the technical detail, and comes back', async () => {
    await renderPage();
    await act(async () => container.querySelector('.pgx-card[data-med="Clopidogrel"]').click());
    expect(container.querySelector('.pgx-card')).toBeNull();
    expect(container.querySelector('#pgx-detail-title').textContent).toBe('Clopidogrel');
    expect(container.querySelector('dt').textContent).toBe('CYP2C19 *1/*2');
    expect(container.querySelector('dd').textContent).toBe('Metabolizador intermedio');
    expect(document.activeElement.textContent).toBe('Medicamentos');
    await act(async () => document.activeElement.click());
    expect(container.querySelector('.pgx-card[data-med="Clopidogrel"]')).not.toBeNull();
  });

  it('keeps the medications you pick in your velador and dims the rest without moving them', async () => {
    await renderPage();
    const input = container.querySelector('input[role="combobox"]');
    await act(async () => { input.focus(); });
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    await act(async () => { set.call(input, 'acidez'); input.dispatchEvent(new Event('input', { bubbles: true })); });
    expect([...container.querySelectorAll('[role="option"]')].map((o) => o.firstChild.textContent)).toEqual(['Omeprazol']);
    await act(async () => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })));
    expect(container.querySelector('.pgx-velador').textContent).toContain('Omeprazol');
    expect(container.querySelector('.pgx-card.is-mine').dataset.med).toBe('Omeprazol');
    expect(container.querySelector('.pgx-group').classList.contains('is-dim')).toBe(true);
    expect([...container.querySelectorAll('.pgx-card')].map((c) => c.dataset.med)).toEqual(['Clopidogrel', 'Omeprazol']);
    await act(async () => container.querySelector('[aria-label="Quitar Omeprazol"]').click());
    expect(container.querySelector('.pgx-velador')).toBeNull();
  });

  it('shows each gene with its medications in the gene lens', async () => {
    await renderPage();
    await act(async () => [...container.querySelectorAll('.pgx-lens button')].find((b) => b.textContent === 'Por gen').click());
    const gene = container.querySelector('.pgx-card--gene');
    expect(gene.querySelector('.pgx-card__name').textContent).toBe('CYP2C19');
    expect([...gene.querySelectorAll('.pgx-chips button')].map((b) => b.textContent)).toEqual(['Clopidogrel', 'Omeprazol']);
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
      // the page's own shape: the real title, the search and lens words, six medication cards waiting
      expect(container.querySelector('main h1').textContent).toBe('Tus remedios');
      expect(getStatus().querySelectorAll('.pgx-cards .pgx-card--ghost')).toHaveLength(6);
      expect(getStatus().querySelector('.pgx-search').textContent).toBe('Busca un medicamento');
      expect(getStatus().querySelector('[aria-hidden="true"]').contains(getStatus().querySelector('.pgx-cards'))).toBe(true);
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
    expect(container.querySelector('.pgx-card__say').textContent).toContain('casi no activa el clopidogrel');
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
    expect(container.querySelector('.pgx-card__say').textContent).toContain('más despacio');
    expect(getStatus().textContent).toContain('disponibles');
  });

  it('shows normalized results while the independent ME profile is still pending', async () => {
    apiRequest.mockImplementationOnce(() => new Promise(() => {}));
    await renderPage();
    expect(container.querySelector('.pgx-card__say').textContent).toContain('más despacio');
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
