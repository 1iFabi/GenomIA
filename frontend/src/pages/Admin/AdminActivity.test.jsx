import React, { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import AdminActivity from './AdminActivity';
import { flush, mountPage, unmountPage } from './testUtils';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(), apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: { id: 1, first_name: 'Admin' } }) }));
vi.mock('../../components/ResultsBar/ResultsBar', () => ({ default: () => <nav aria-label="Secciones" /> }));

const CURSOR = '2026-11-20T10:00:00+00:00';
const event = (n, extra = {}) => ({
  id: `reception:${n}`, kind: 'reception', at: '2026-11-26T14:00:00-03:00', action: 'verify_rut', outcome: 'no_match',
  actor: { id: 4, name: 'Rosa Rec', email: 'rosa@genomia.dev', role: 'RECEPCION' },
  subject: { id: 9, name: 'Juan Soto', email: 'juan@gmail.com', sample_code: 'GX-0042' },
  ...extra,
});
let pages;
const params = (call) => new URL(call[0], 'http://x').searchParams;
const activityCalls = () => apiRequest.mock.calls.filter(([url]) => url.startsWith(API_ENDPOINTS.ADMIN_ACTIVITY));
const rows = (view) => [...view.querySelectorAll('tr.pgx-row')];

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  apiRequest.mockReset();
  pages = [{ events: [event(1), event(2)], next_before: CURSOR }, { events: [event(3)], next_before: null }];
  apiRequest.mockImplementation(async (url) => {
    const before = new URL(url, 'http://x').searchParams.get('before');
    return { ok: true, data: before ? pages[1] : pages[0] };
  });
});
afterEach(async () => { await unmountPage(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('AdminActivity', () => {
  it('lists who did what to whom, and opens the outcome', async () => {
    const view = await mountPage(<AdminActivity />, '/dashboard/admin/actividad');
    await flush();
    expect(rows(view)).toHaveLength(2);
    const first = rows(view)[0].textContent;
    expect(first).toContain('Rosa Rec');
    expect(first).toContain('Verificó un RUT');
    expect(first).toContain('Juan Soto');
    await act(async () => rows(view)[0].querySelector('.pgx-row__name').click());
    const detail = view.querySelector('.pgx-row-detail').textContent;
    expect(detail).toContain('No coincide');
    expect(detail).toContain('GX-0042');
    expect(detail).toContain('juan@gmail.com');
  });

  it('asks again by kind when a filter is chosen', async () => {
    const view = await mountPage(<AdminActivity />, '/dashboard/admin/actividad');
    await flush();
    const chip = [...view.querySelectorAll('.adm-tab')].find((c) => c.textContent === 'Recepción');
    await act(async () => chip.click());
    await flush();
    expect(params(activityCalls().at(-1)).get('kind')).toBe('reception');
  });

  it('searches by name or email after a short pause', async () => {
    const view = await mountPage(<AdminActivity />, '/dashboard/admin/actividad');
    await flush();
    vi.useFakeTimers();
    const input = view.querySelector('.pgx-search input');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    await act(async () => { setter.call(input, 'juan'); input.dispatchEvent(new Event('input', { bubbles: true })); });
    const before = activityCalls().length;
    await act(async () => { vi.advanceTimersByTime(299); });
    expect(activityCalls()).toHaveLength(before);
    await act(async () => { vi.advanceTimersByTime(1); });
    vi.useRealTimers();
    await flush();
    expect(params(activityCalls().at(-1)).get('q')).toBe('juan');
  });

  it('loads more with the cursor, then hides the button', async () => {
    const view = await mountPage(<AdminActivity />, '/dashboard/admin/actividad');
    await flush();
    const more = () => [...view.querySelectorAll('button')].find((b) => b.textContent === 'Cargar más');
    await act(async () => more().click());
    await flush();
    expect(params(activityCalls().at(-1)).get('before')).toBe(CURSOR);
    expect(rows(view)).toHaveLength(3);
    expect(more()).toBeUndefined();
  });

  it('says so when there is no activity', async () => {
    pages[0] = { events: [], next_before: null };
    const view = await mountPage(<AdminActivity />, '/dashboard/admin/actividad');
    await flush();
    expect(view.textContent).toContain('Aún no hay actividad registrada');
  });

  it('shows a deleted account and a look-up with nobody found', async () => {
    pages[0] = { events: [event(1, { subject: null, action: 'search', outcome: '0 result(s)' }),
      event(2, { kind: 'genetic', action: 'results', actor: { id: 7, name: 'Cuenta eliminada', email: null, role: null },
        subject: { id: 7, name: 'Cuenta eliminada', email: null, sample_code: null } })], next_before: null };
    const view = await mountPage(<AdminActivity />, '/dashboard/admin/actividad');
    await flush();
    expect(rows(view)[0].textContent).toContain('Sin resultado');
    expect(rows(view)[1].textContent).toContain('Cuenta eliminada');
  });
});
