import React, { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import AdminUsers from './AdminUsers';
import { flush, mountPage, unmountPage } from './testUtils';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(), apiRequest: vi.fn(), clearToken: vi.fn(),
}));
vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: { id: 1, first_name: 'Admin' } }) }));
vi.mock('../../components/ResultsBar/ResultsBar', () => ({ default: () => <nav aria-label="Secciones" /> }));

const row = (id, first, email, role, extra = {}) => ({
  id, username: `u${id}`, email, first_name: first, last_name: 'Pérez', roles: role ? [role] : [],
  is_admin: role === 'ADMIN', is_analyst: role === 'ANALISTA', is_reception: role === 'RECEPCION',
  service_status: 'NO_PURCHASED', date_joined: '2026-10-01T10:00:00-03:00', last_login: null, ...extra,
});
const USERS = [
  row(1, 'Admin', 'admin@genomia.dev', 'ADMIN'),
  row(2, 'Ana', 'ana@genomia.dev', 'ANALISTA'),
  row(3, 'Juan', 'juan.soto@gmail.com', 'CLIENTE', { service_status: 'PENDING', last_login: '2026-11-20T09:00:00-03:00' }),
  row(4, 'Rosa', 'rosa@genomia.dev', 'RECEPCION'),
  row(5, 'Otra', 'otra-admin@genomia.dev', 'ADMIN'),
];
let saveReply;
const respond = () => apiRequest.mockImplementation(async (url) => {
  if (url === API_ENDPOINTS.GET_USERS) return { ok: true, data: USERS };
  if (url === API_ENDPOINTS.ADMIN_ANALYSTS) return saveReply;
  return { ok: false, data: {} };
});
const rows = (view) => [...view.querySelectorAll('tr.pgx-row')];
const rowOf = (view, email) => rows(view).find((r) => r.textContent.includes(email));
const open = async (view, email) => { await act(async () => rowOf(view, email).querySelector('.pgx-row__name').click()); };
const pick = async (view, label) => {
  const input = [...view.querySelectorAll('.adm-roles label')].find((l) => l.textContent === label).querySelector('input');
  await act(async () => input.click());
};
const save = async (view) => { await act(async () => view.querySelector('.adm-save').click()); await flush(); };
const type = async (view, value) => {
  const input = view.querySelector('.pgx-search input');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
};
const posted = () => JSON.parse(apiRequest.mock.calls.find(([url]) => url === API_ENDPOINTS.ADMIN_ANALYSTS)[1].body);

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  apiRequest.mockReset();
  saveReply = { ok: true, data: { is_analyst: false, is_reception: true } };
  respond();
});
afterEach(async () => { await unmountPage(); vi.unstubAllGlobals(); });

describe('AdminUsers', () => {
  it('lists name, email, role and service, and finds a user by part of the email', async () => {
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    expect(rows(view)).toHaveLength(5);
    expect(rowOf(view, 'juan.soto@gmail.com').textContent).toContain('Cliente');
    expect(rowOf(view, 'juan.soto@gmail.com').textContent).toContain('Pendiente');
    await type(view, 'soto@');
    expect(rows(view)).toHaveLength(1);
  });

  it('counts and filters by role, starting from ?rol=', async () => {
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios?rol=ANALISTA');
    await flush();
    expect(rows(view)).toHaveLength(1);
    const admins = [...view.querySelectorAll('.adm-tab')].find((c) => c.textContent.startsWith('Admin'));
    expect(admins.textContent).toContain('2');
    await act(async () => admins.click());
    expect(rows(view)).toHaveLength(2);
  });

  it('opens a row with its dates and the role choice', async () => {
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    await open(view, 'juan.soto@gmail.com');
    const detail = view.querySelector('.pgx-row-detail').textContent;
    expect(detail).toContain('Alta');
    expect(detail).toContain('Último ingreso');
    expect(view.querySelectorAll('.adm-roles input')).toHaveLength(3);
    await open(view, 'ana@genomia.dev');
    expect(view.querySelector('.pgx-row-detail').textContent).toContain('Nunca');
  });

  it('grants reception and moves the row to it', async () => {
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    await open(view, 'juan.soto@gmail.com');
    await pick(view, 'Recepción');
    await save(view);
    expect(posted()).toEqual({ userId: 3, grant: true, role: 'reception' });
    expect(rowOf(view, 'juan.soto@gmail.com').textContent).toContain('Recepción');
  });

  it('takes the special access away from an analyst', async () => {
    saveReply = { ok: true, data: { is_analyst: false, is_reception: false } };
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    await open(view, 'ana@genomia.dev');
    await pick(view, 'Sin acceso especial');
    await save(view);
    expect(posted()).toEqual({ userId: 2, grant: false, role: 'analyst' });
    expect(rowOf(view, 'ana@genomia.dev').textContent).toContain('Cliente');
  });

  it('keeps the role and shows the error when the server refuses', async () => {
    saveReply = { ok: false, status: 409, data: { error: 'No se puede cambiar el rol de un administrador' } };
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    await open(view, 'juan.soto@gmail.com');
    await pick(view, 'Analista');
    await save(view);
    expect(view.querySelector('.adm-msg--error').textContent).toBe('No se puede cambiar el rol de un administrador');
    expect(rowOf(view, 'juan.soto@gmail.com').textContent).toContain('Cliente');
  });

  it('gives admins and the signed-in user no role control', async () => {
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    await open(view, 'otra-admin@genomia.dev');
    expect(view.querySelector('.adm-roles')).toBeNull();
    await open(view, 'admin@genomia.dev');
    expect(view.querySelector('.adm-roles')).toBeNull();
  });

  it('offers a retry when the list fails', async () => {
    apiRequest.mockResolvedValue({ ok: false, data: { error: 'x' } });
    const view = await mountPage(<AdminUsers />, '/dashboard/admin/usuarios');
    await flush();
    expect(view.querySelector('[role="alert"]')).not.toBeNull();
    respond();
    await act(async () => [...view.querySelectorAll('button')].find((b) => b.textContent === 'Reintentar').click());
    await flush();
    expect(rows(view)).toHaveLength(5);
  });
});
