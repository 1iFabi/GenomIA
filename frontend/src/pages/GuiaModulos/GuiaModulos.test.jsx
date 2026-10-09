import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../config/api';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { AuthProvider } from '../../contexts/AuthContext';
import GuiaModulos from './GuiaModulos';

vi.mock('../../hooks/useLatestGenomicsResults', () => ({ useLatestGenomicsResults: vi.fn() }));
vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(), apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('../../components/Sidebar/Sidebar', () => ({
  default: ({ items }) => (
    <nav aria-label="Dashboard navigation">
      {items.map((item) => <Link key={item.href} to={item.href}>{item.label}</Link>)}
    </nav>
  ),
}));

const traits = Array.from({ length: 12 }, (_, index) => ({
  trait: `t${index}`, label: `Rasgo ${index}`, category: 'Metabolismo', result: 'Rápido',
  explanation: 'Explicación.', description: 'Descripción.', gene: 'CYP1A2', rsid: 'rs762551',
}));
const readyState = () => ({
  status: 'ready', loading: false, error: null, retry: vi.fn(),
  data: {
    disclaimer: 'Resultados de desarrollo.',
    modules: {
      global_ancestry: [{ population: 'MAP', label: 'Mapuche', country: 'Chile', country_code: 'CL', group_label: 'Amerindio', proportion: 0.3 }],
      pharmacogenetics: [{ gene: 'CYP2D6', diplotype: '*1/*4', phenotype: 'Metabolizador intermedio', drugs: ['Codeína', 'Tramadol'] }],
      traits,
    },
    variants: [],
  },
});

let root;
let container;
const renderPage = async () => {
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/dashboard/modulos']}>
      <AuthProvider><GuiaModulos /></AuthProvider>
    </MemoryRouter>
  ));
};
const card = (key) => container.querySelector(`[aria-labelledby="guia-${key}-title"]`);

beforeEach(() => {
  vi.resetAllMocks();
  apiRequest.mockResolvedValue({ ok: true, data: { user: { name: 'Ada' } } });
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

describe('GuiaModulos', () => {
  it('describes every module and shows the client rows under the backend field names', async () => {
    useLatestGenomicsResults.mockReturnValue(readyState());
    await renderPage();
    expect([...container.querySelectorAll('.guia-card h2')].map((title) => title.textContent)).toEqual([
      'Ancestría global', 'Ancestría local', 'Riesgo monogénico', 'Riesgo poligénico', 'Farmacogenética',
      'Rasgos', 'Variantes asignadas (base)',
    ]);
    const ancestry = card('global_ancestry');
    expect([...ancestry.querySelectorAll('th')].map((th) => th.textContent))
      .toEqual(['label', 'country', 'country_code', 'group_label', 'proportion']);
    expect([...ancestry.querySelectorAll('td')].map((td) => td.textContent))
      .toEqual(['Mapuche', 'Chile', 'CL', 'Amerindio', '0.3000']);
    expect(card('pharmacogenetics').querySelector('tbody').textContent).toContain('Codeína, Tramadol');
    expect(card('local_ancestry').textContent).toContain('no tiene filas para este módulo');
    expect(card('traits').querySelectorAll('tbody tr')).toHaveLength(10);
    expect(card('traits').textContent).toContain('… y 2 filas más.');
    expect(card('traits').querySelector('a').getAttribute('href')).toBe('/dashboard/rasgos');
    expect(container.textContent).toContain('Resultados de desarrollo.');
  });

  it('keeps reference text visible while only the personal module data is loading', async () => {
    useLatestGenomicsResults.mockReturnValue({ status: 'loading', loading: true, data: null, error: null, retry: vi.fn() });
    await renderPage();
    expect(container.querySelectorAll('.guia-card')).toHaveLength(7);
    expect(card('global_ancestry').querySelector('.guia-card__what')?.textContent).toContain('Qué proporción');
    expect(container.querySelectorAll('.guia-card__loading')).toHaveLength(7);
    expect(container.querySelector('.guia-card__empty')).toBeNull();
    expect(container.querySelector('.guia-loading-status')?.getAttribute('role')).toBe('status');
  });

  it('keeps the module descriptions without data and lists the guide in the navigation', async () => {
    useLatestGenomicsResults.mockReturnValue({ status: 'empty', loading: false, data: null, error: null, retry: vi.fn() });
    await renderPage();
    expect(container.querySelectorAll('.guia-card')).toHaveLength(7);
    expect(container.querySelector('table')).toBeNull();
    expect(container.querySelector('[role="status"]').textContent).toContain('Aún no tienes resultados');
    expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href'))).toContain('/dashboard/modulos');
  });
});
