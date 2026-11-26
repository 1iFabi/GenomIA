import React, { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import AdminOverview from './AdminOverview';
import { flush, mountPage, unmountPage } from './testUtils';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(), apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: { first_name: 'Admin' } }) }));
vi.mock('../../components/ResultsBar/ResultsBar', () => ({ default: () => <nav aria-label="Secciones" /> }));

const overview = {
  clients: 12, purchases_pending: 2, services_open: 5, services_completed: 7,
  stages: [
    { code: 'WAITING_SAMPLE', count: 2, oldest_days: 3 },
    { code: 'SAMPLE_RECEIVED', count: 0, oldest_days: null },
    { code: 'PROCESSING', count: 3, oldest_days: 9 },
    { code: 'COMPLETED', count: 7, oldest_days: null },
  ],
  staff: { ADMIN: 1, ANALISTA: 2, RECEPCION: 1 },
  generated_at: '2026-11-26T15:00:00-03:00',
};
const event = (n) => ({
  id: `status:${n}`, kind: 'status', at: '2026-11-26T14:00:00-03:00', action: 'PROCESSING', outcome: null,
  actor: { id: 3, name: `Analista ${n}`, email: 'a@x.cl', role: 'ANALISTA' },
  subject: { id: 9, name: 'Juan Soto', email: 'juan@x.cl', sample_code: 'GX-1' },
});
const respond = ({ failOverview = false } = {}) => apiRequest.mockImplementation(async (url) => {
  if (url === API_ENDPOINTS.ADMIN_OVERVIEW) return failOverview ? { ok: false, data: { error: 'x' } } : { ok: true, data: overview };
  if (url.startsWith(API_ENDPOINTS.ADMIN_ACTIVITY)) return { ok: true, data: { events: [1, 2, 3, 4, 5, 6].map(event), next_before: null } };
  return { ok: false, data: {} };
});
const text = (view) => view.textContent.replace(/\s+/g, ' ');

beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); apiRequest.mockReset(); });
afterEach(async () => { await unmountPage(); vi.unstubAllGlobals(); });

describe('AdminOverview', () => {
  it('shows the four figures', async () => {
    respond();
    const view = await mountPage(<AdminOverview />);
    await flush();
    const figures = [...view.querySelectorAll('.adm-figure')].map((f) => [f.querySelector('dt').textContent, f.querySelector('dd').textContent]);
    expect(figures).toEqual([['Clientes', '12'], ['Compras sin pagar', '2'], ['Servicios en curso', '5'], ['Informes listos', '7']]);
  });

  it('shows the stages in order with the oldest waiting time', async () => {
    respond();
    const view = await mountPage(<AdminOverview />);
    await flush();
    const stages = [...view.querySelectorAll('.adm-stage')];
    expect(stages.map((s) => s.querySelector('.adm-stage__name').textContent)).toEqual(['Esperando muestra', 'Muestra recibida', 'En proceso', 'Completado']);
    expect(text(stages[2])).toContain('hace 9 días');
  });

  it('says today instead of zero days', async () => {
    overview.stages[0].oldest_days = 0;
    respond();
    const view = await mountPage(<AdminOverview />);
    await flush();
    overview.stages[0].oldest_days = 3;
    expect(view.querySelectorAll('.adm-stage')[0].textContent).toContain('El más antiguo, de hoy');
  });

  it('links staff counts to the filtered user list', async () => {
    respond();
    const view = await mountPage(<AdminOverview />);
    await flush();
    const analysts = [...view.querySelectorAll('.adm-staff a')].find((a) => a.textContent.includes('Analistas'));
    expect(analysts.getAttribute('href')).toBe('/dashboard/admin/usuarios?rol=ANALISTA');
    expect(analysts.textContent).toContain('2');
  });

  it('lists the five latest events and links to the whole activity', async () => {
    respond();
    const view = await mountPage(<AdminOverview />);
    await flush();
    expect(view.querySelectorAll('.adm-feed li')).toHaveLength(5);
    expect(text(view.querySelector('.adm-feed'))).toContain('Movió el servicio a En proceso');
    expect([...view.querySelectorAll('a')].find((a) => a.textContent === 'Ver toda la actividad').getAttribute('href')).toBe('/dashboard/admin/actividad');
  });

  it('offers a retry when the figures fail, and loads again', async () => {
    respond({ failOverview: true });
    const view = await mountPage(<AdminOverview />);
    await flush();
    expect(view.querySelector('[role="alert"]')).not.toBeNull();
    respond();
    await act(async () => [...view.querySelectorAll('button')].find((b) => b.textContent === 'Reintentar').click());
    await flush();
    expect(view.querySelectorAll('.adm-figure')).toHaveLength(4);
  });

  it('shows the skeleton while it loads', async () => {
    apiRequest.mockImplementation(() => new Promise(() => {}));
    const view = await mountPage(<AdminOverview />);
    expect(view.querySelector('[aria-busy="true"] .pgx-skel')).not.toBeNull();
  });
});
