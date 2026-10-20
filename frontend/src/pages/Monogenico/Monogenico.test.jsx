import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { AuthProvider } from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/ProtectedRoute';
import Monogenico from './Monogenico';

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
const makeHealth = () => ({
  variant_id: 'v-brca2', contig: '13', position: 32340300, clinical_significance: 'Pathogenic',
  gene: 'BRCA2', conditions: ['Cáncer de mama y ovario hereditario'], zygosity: 'heterocigoto',
  review_status: 'reviewed_by_expert_panel', review_stars: 3, inheritance: 'AD',
  hgvs: 'NM_000059.4:c.5946del', clinvar_id: 'VCV000009322', source: 'ClinVar',
});
const makeHomozygous = () => ({
  ...makeHealth(), variant_id: 'v-hfe', gene: 'HFE', conditions: ['Hemocromatosis hereditaria tipo 1'],
  zygosity: 'homocigoto', inheritance: 'AR', hgvs: 'NM_000410.4:c.845G>A', clinvar_id: 'VCV000000009',
});
const makeCarrier = () => ({
  ...makeHealth(), variant_id: 'v-cftr', gene: 'CFTR', conditions: ['Fibrosis quística'],
  inheritance: 'AR', review_status: 'practice_guideline', review_stars: 4,
  hgvs: 'NM_000492.4:c.1521_1523del', clinvar_id: 'VCV000007105',
});
const makeUncured = () => ({
  ...makeHealth(), variant_id: 'v-tnni3', gene: 'TNNI3', conditions: [],
  inheritance: null, review_status: 'criteria_provided,_single_submitter', review_stars: 1,
  hgvs: 'NM_000363.5:c.433C>T', clinvar_id: 'VCV000043395',
});
const variants = [makeHealth(), makeHomozygous(), makeCarrier(), makeUncured()];
const makeState = () => ({
  status: 'ready', loading: false, error: null, retry: vi.fn(),
  data: { disclaimer, sample_code: 'SEED-1', modules: { monogenic_risk: variants.map((v) => ({ ...v })) } },
});

let state;
let root;
let container;
function LocationMarker() {
  return <output aria-label="Current route">{useLocation().pathname}</output>;
}
const renderPage = async ({ protectedRoute = false } = {}) => {
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/dashboard/enfermedades#monogenic_risk']}>
      <AuthProvider>
        {protectedRoute ? (
          <React.StrictMode><ProtectedRoute><Monogenico /></ProtectedRoute></React.StrictMode>
        ) : <Monogenico />}
        <LocationMarker />
      </AuthProvider>
    </MemoryRouter>
  ));
};
const tab = (key) => container.querySelector(`[role="tab"][data-q="${key}"]`);
const rowButton = (gene) => [...container.querySelectorAll('.row__head')]
  .find((button) => button.querySelector('.row__gene').textContent === gene);
const getStatus = () => container.querySelector('main [role="status"], main [role="alert"]');
const getRetry = () => [...container.querySelectorAll('main button')]
  .find((button) => button.textContent === 'Reintentar');
const expectNoDisplay = () => {
  expect(container.querySelector('.row')).toBeNull();
  expect(container.querySelector('.tabs')).toBeNull();
  expect(container.querySelector('.empty')).toBeNull();
};
const expectShell = () => {
  expect(container.querySelector('main h1').textContent).toBe('Gen por gen');
  expect(container.querySelector('main.mono-main-content')).not.toBeNull();
  expect(container.querySelector('nav[aria-label="Dashboard navigation"]')).not.toBeNull();
};

beforeEach(() => {
  vi.resetAllMocks();
  state = makeState();
  useLatestGenomicsResults.mockImplementation(() => state);
  apiRequest.mockResolvedValue({ ok: true, data: { user: { name: 'Demo account' } } });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
});

describe('monogenic risk page', () => {
  it('reads the variant count and splits it into the three questions', async () => {
    await renderPage();
    expectShell();
    expect(container.querySelector('.lede').textContent)
      .toBe('4 variantes, y no todas significan lo mismo. Toca un gen para ver qué significa y qué no.');
    expect(tab('salud').querySelector('.tab__n').textContent).toBe('2');
    expect(tab('transmitir').querySelector('.tab__n').textContent).toBe('1');
    expect(tab('conversar').querySelector('.tab__n').textContent).toBe('1');
    expect(tab('salud').getAttribute('aria-selected')).toBe('true');
    expect(tab('salud').textContent).toContain('¿Puede afectar mi salud?');
    expect(container.querySelector('.notmean').textContent).toContain('No significa que vayas a desarrollar la condición');
    expect(getStatus().textContent).toBe('Datos disponibles.');
    expect(container.textContent).toContain('Esto no es un diagnóstico.');
    expect(container.textContent).not.toContain('Preparar hoja para tu genetista');
    expect(container.textContent).not.toContain('coordenadas GRCh38');
  });

  it('sorts known inheritance first and two copies before one, each row drawing its copies', async () => {
    await renderPage();
    expect([...container.querySelectorAll('.list[data-q="salud"] .row__gene')].map((gene) => gene.textContent))
      .toEqual(['HFE', 'BRCA2']);
    const hfe = rowButton('HFE');
    expect(hfe.querySelector('.copies').getAttribute('aria-label')).toBe('Las dos copias del gen tienen la variante');
    expect(hfe.querySelectorAll('.copies i.is-var')).toHaveLength(2);
    const brca2 = rowButton('BRCA2');
    expect(brca2.querySelector('.copies').getAttribute('aria-label')).toBe('Una de tus dos copias tiene la variante');
    expect(brca2.querySelectorAll('.copies i.is-var')).toHaveLength(1);
  });

  it('switches questions by click and by arrow keys', async () => {
    await renderPage();
    await act(async () => tab('transmitir').click());
    expect(tab('transmitir').getAttribute('aria-selected')).toBe('true');
    expect(container.querySelector('.list[data-q="salud"]').hidden).toBe(true);
    expect(container.querySelector('.list[data-q="transmitir"]').hidden).toBe(false);
    expect(container.querySelector('.list[data-q="transmitir"] .notmean').textContent).toContain('Tus hijos solo podrían tenerla');
    expect(rowButton('CFTR')).not.toBeUndefined();
    await act(async () => {
      tab('transmitir').focus();
      container.querySelector('[role="tablist"]').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
      );
    });
    expect(document.activeElement).toBe(tab('conversar'));
    expect(tab('conversar').getAttribute('aria-selected')).toBe('true');
  });

  it('opens a row in place with the consequence, the certainty and the technical detail', async () => {
    await renderPage();
    const button = rowButton('BRCA2');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    await act(async () => button.click());
    expect(button.getAttribute('aria-expanded')).toBe('true');
    const detail = document.getElementById(button.getAttribute('aria-controls'));
    expect(detail.querySelector('.detail__say').textContent).toContain('Con una copia basta');
    expect(detail.querySelector('.detail__cert').textContent).toBe('Evidencia bien establecida');
    expect([...detail.querySelectorAll('.facts dt')].map((dt) => dt.textContent))
      .toEqual(['Cómo se hereda', 'Tus copias', 'Qué tan segura es']);
    expect(detail.querySelector('.facts').textContent).toContain('Autosómica dominanteBasta una copia alterada');
    expect(detail.querySelector('.facts').textContent).toContain('Una de dos');
    expect(detail.querySelector('.facts').textContent).toContain('panel de expertos');
    expect(detail.querySelector('details.techbox').open).toBe(false);
    expect(detail.querySelectorAll('.tech dt')).toHaveLength(4);
    expect(detail.querySelector('.tech').textContent).toContain('Patogénica, 3 de 4 estrellas en ClinVar');
    expect(detail.querySelector('.tech').textContent).toContain('NM_000059.4:c.5946del');
    expect(detail.querySelector('.tech a').getAttribute('href'))
      .toBe('https://www.ncbi.nlm.nih.gov/clinvar/variation/VCV000009322/');
    expect(detail.querySelector('.tech').textContent).toContain('chr13:32340300');
    await act(async () => button.click());
    expect(container.querySelector('.detail')).toBeNull();
  });

  it('says two copies may express and an uncured mode is only for talking over', async () => {
    await renderPage();
    await act(async () => rowButton('HFE').click());
    expect(container.querySelector('.detail__say').textContent).toContain('las dos copias alteradas');
    await act(async () => rowButton('HFE').click());
    await act(async () => tab('conversar').click());
    const button = rowButton('TNNI3');
    await act(async () => button.click());
    const detail = document.getElementById(button.getAttribute('aria-controls'));
    expect(detail.querySelector('.detail__say').textContent).toContain('no tenemos curado');
    expect(detail.querySelector('.detail__cert').textContent).toBe('Revisión limitada');
    expect(detail.querySelector('.facts').textContent).toContain('Aún no curada');
    expect(button.querySelector('.row__cond').textContent).toBe('Condición no informada');
  });

  it('groups the variants of one gene into one row that keeps each variant in the technical data', async () => {
    state.data.modules.monogenic_risk = [
      makeCarrier(),
      { ...makeCarrier(), variant_id: 'v-cftr-2', conditions: ['Fibrosis quística', 'Pancreatitis hereditaria'],
        hgvs: 'NM_000492.4:c.350G>A', review_stars: 2 },
    ];
    await renderPage();
    expect(container.querySelector('.lede').textContent).toContain('2 variantes en un gen');
    expect(tab('transmitir').querySelector('.tab__n').textContent).toBe('1');
    expect(container.querySelectorAll('.row')).toHaveLength(1);
    const button = rowButton('CFTR');
    expect(button.querySelector('.row__cond').textContent).toBe('Fibrosis quística, Pancreatitis hereditaria');
    await act(async () => button.click());
    const detail = document.getElementById(button.getAttribute('aria-controls'));
    expect(detail.querySelector('.techbox summary').textContent)
      .toBe('Datos técnicos para tu especialista (2 variantes en CFTR)');
    expect([...detail.querySelectorAll('.tech')].map((dl) => dl.querySelector('dd').textContent))
      .toEqual(['NM_000492.4:c.1521_1523del', 'NM_000492.4:c.350G>A']);
    expect(detail.querySelector('.detail__cert').textContent).toBe('Evidencia bien establecida');
  });

  it('shows the designed empty state when the module has no pathogenic variants', async () => {
    state.data.modules.monogenic_risk = [];
    await renderPage();
    expectShell();
    expect(container.querySelector('.lede').textContent)
      .toBe('En lo que cubre tu análisis no encontramos variantes patogénicas.');
    expect(container.querySelector('.empty h2').textContent).toBe('Sin variantes patogénicas en tu muestra');
    expect(container.querySelector('.empty').textContent).toContain('No cubre todo el genoma');
    expect(container.querySelector('.tabs')).toBeNull();
    expect(container.textContent).toContain('Esto no es un diagnóstico.');
  });

  it('reports a missing module when the service only has other results', async () => {
    state.data.modules = { traits: [{ trait: 'cafeina', label: 'Cafeína', result: 'Rápido' }] };
    await renderPage();
    expectNoDisplay();
    expect(getStatus().textContent).toContain('no tiene resultados de riesgo monogénico');
  });

  it('reuses the StrictMode guard profile and requests only the shared ME profile', async () => {
    await renderPage({ protectedRoute: true });
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    await renderPage();
    expect(container.querySelector('nav').textContent).toContain('Demo account');
    expect(useLatestGenomicsResults).toHaveBeenCalled();
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(API_ENDPOINTS.ME, { method: 'GET' });
  });
});

const stateCases = [
  ['loading', { status: 'loading', loading: true, data: null }, 'Cargando datos', 'status'],
  ['empty', { status: 'empty', data: null }, 'Aún no tienes resultados', 'status'],
  ['permission', { status: 'permission', data: null, error: { status: 403 } }, 'No tienes permiso', 'alert'],
  ['connection error', { status: 'error', data: null, error: { kind: 'connection', status: 0 } }, 'No fue posible cargar', 'alert'],
  ['HTTP error', { status: 'error', data: null, error: { kind: 'http', status: 500 } }, 'No fue posible cargar', 'alert'],
];
describe('result states', () => {
  it.each(stateCases)('keeps the title and the shell in %s without stale values', async (_name, override, message, role) => {
    Object.assign(state, override);
    await renderPage();
    expectShell();
    expectNoDisplay();
    expect(getStatus().textContent).toContain(message);
    expect(getStatus().getAttribute('role')).toBe(role);
    expect(getStatus().getAttribute('aria-busy')).toBe(String(Boolean(override.loading)));
    if (override.loading) {
      expect(container.querySelectorAll('.mono-skel-tab')).toHaveLength(3);
      expect(container.querySelectorAll('.mono-skel-row')).toHaveLength(4);
    }
    expect(Boolean(getRetry())).toBe(!override.loading);
    expect(container.querySelector('nav').textContent).toContain('Demo account');
  });

  it('uses the named hook retry', async () => {
    Object.assign(state, stateCases[2][1]);
    await renderPage();
    await act(async () => getRetry().click());
    expect(state.retry).toHaveBeenCalledTimes(1);
  });

  it('drops the display during a retry and shows only the next normalized response', async () => {
    await renderPage();
    state = { ...state, status: 'loading', loading: true, data: null };
    await renderPage();
    expectNoDisplay();
    state = makeState();
    state.data.modules.monogenic_risk = [makeCarrier()];
    await renderPage();
    expect(container.querySelector('.lede').textContent)
      .toBe('Una variante, y ninguna cambia tu salud hoy. Toca un gen para ver qué significa.');
    expect(tab('transmitir').querySelector('.tab__n').textContent).toBe('1');
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
  });

  it.each(['ready', 'loading', 'permission', 'error'])('clears the session and navigates home on logout in %s', async (status) => {
    Object.assign(state, { status, loading: status === 'loading' });
    await renderPage();
    await act(async () => [...container.querySelectorAll('nav button')]
      .find((button) => button.textContent === 'Cerrar sesión').click());
    expect(clearToken).toHaveBeenCalledExactlyOnceWith();
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/');
  });
});
