import React, { Fragment, useCallback, useEffect, useId, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronDown, Search, X } from 'lucide-react';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import { useSession } from '../../hooks/useSession';
import AdminShell from './AdminShell';

const ROLE_LABEL = { CLIENTE: 'Cliente', ANALISTA: 'Analista', RECEPCION: 'Recepción', ADMIN: 'Administrador' };
const FILTERS = [['', 'Todos'], ['CLIENTE', 'Clientes'], ['ANALISTA', 'Analistas'], ['RECEPCION', 'Recepción'], ['ADMIN', 'Administradores']];
const SERVICE_LABEL = { NO_PURCHASED: 'Sin servicio', PENDING: 'Pendiente', COMPLETED: 'Completado' };
// The role choice an admin can make; the server holds one privileged role at a time.
const CHOICES = [['none', 'Sin acceso especial'], ['analyst', 'Analista'], ['reception', 'Recepción']];
const CHOICE_OF = { ANALISTA: 'analyst', RECEPCION: 'reception' };

const roleOf = (u) => u.roles?.[0] ?? 'CLIENTE';
const nameOf = (u) => `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username || u.email;
const DAY = new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'short', year: 'numeric' });
const day = (iso) => (iso ? DAY.format(new Date(iso)) : 'Nunca');

const RoleForm = ({ user, onSaved }) => {
  const current = CHOICE_OF[roleOf(user)] ?? 'none';
  const [choice, setChoice] = useState(current);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const name = useId();

  const save = async () => {
    setSaving(true);
    setMessage(null);
    const body = choice === 'none'
      ? { userId: user.id, grant: false, role: current }
      : { userId: user.id, grant: true, role: choice };
    const resp = await apiRequest(API_ENDPOINTS.ADMIN_ANALYSTS, { method: 'POST', body: JSON.stringify(body) });
    setSaving(false);
    if (!resp.ok) {
      setMessage({ error: true, text: resp.data?.error || 'No se pudo cambiar el rol.' });
      return;
    }
    const role = resp.data?.is_analyst ? 'ANALISTA' : resp.data?.is_reception ? 'RECEPCION' : 'CLIENTE';
    onSaved(user.id, role);
    setMessage({ error: false, text: 'Rol actualizado.' });
  };

  return (
    <div className="adm-roles-box">
      <fieldset className="adm-roles">
        <legend>Rol</legend>
        {CHOICES.map(([value, label]) => (
          <label key={value}>
            <input type="radio" name={name} value={value} checked={choice === value} onChange={() => setChoice(value)} />
            {label}
          </label>
        ))}
      </fieldset>
      <button type="button" className="adm-save" disabled={saving || choice === current} onClick={save}>
        {saving ? 'Guardando…' : 'Guardar'}
      </button>
      <p className={message?.error ? 'adm-msg adm-msg--error' : 'adm-msg'} role="status" aria-live="polite">{message?.text}</p>
    </div>
  );
};

const AdminUsers = () => {
  const { user: me } = useSession();
  const [params, setParams] = useSearchParams();
  const [state, setState] = useState({ status: 'loading', users: [] });
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState(null);
  const filter = FILTERS.some(([code]) => code === params.get('rol')) ? params.get('rol') : '';

  const load = useCallback(async () => {
    setState({ status: 'loading', users: [] });
    const resp = await apiRequest(API_ENDPOINTS.GET_USERS, { method: 'GET' });
    setState(resp.ok ? { status: 'ready', users: resp.data || [] } : { status: 'error', users: [] });
  }, []);

  useEffect(() => { load(); }, [load]);

  const counts = useMemo(() => state.users.reduce((acc, u) => ({ ...acc, [roleOf(u)]: (acc[roleOf(u)] || 0) + 1 }), {}), [state.users]);
  const shown = useMemo(() => {
    const term = query.trim().toLowerCase();
    return state.users.filter((u) => (!filter || roleOf(u) === filter)
      && (!term || `${nameOf(u)} ${u.email}`.toLowerCase().includes(term)));
  }, [state.users, filter, query]);

  const setFilter = (code) => setParams(code ? { rol: code } : {}, { replace: true });
  const saved = (id, role) => setState((s) => ({
    ...s, users: s.users.map((u) => (u.id === id ? { ...u, roles: [role] } : u)),
  }));

  return (
    <AdminShell section="admin_users" lede="Las cuentas de GenomIA. Abre una fila para ver sus fechas o cambiar su rol.">
      {state.status === 'loading' && (
        <div className="adm-sheet" role="status" aria-busy="true">
          <span className="pgx-sr">Cargando usuarios…</span>
          {['70%', '55%', '80%', '60%'].map((w) => <span key={w} className="pgx-skel" style={{ '--w': w }} aria-hidden="true" />)}
        </div>
      )}
      {state.status === 'error' && (
        <div className="pgx-status">
          <p role="alert">No se pudo cargar la lista de usuarios.</p>
          <button type="button" className="pgx-retry" onClick={load}>Reintentar</button>
        </div>
      )}
      {state.status === 'ready' && (
        <>
          <ul className="adm-tabs" aria-label="Filtrar por rol">
            {FILTERS.map(([code, label]) => (
              <li key={code || 'all'}>
                <button type="button" className="adm-tab" aria-pressed={filter === code} onClick={() => setFilter(code)}>
                  <span>{label}</span> <b>{code ? counts[code] || 0 : state.users.length}</b>
                </button>
              </li>
            ))}
          </ul>
          <div className="pgx-table adm-table">
            <div className="pgx-table__bar">
              <label className="pgx-search">
                <Search size={17} aria-hidden="true" />
                <span className="pgx-sr">Buscar por nombre o email</span>
                <input type="search" value={query} placeholder="Buscar por nombre o email" onChange={(e) => setQuery(e.target.value)} />
                {query && (
                  <button type="button" className="pgx-search__clear" aria-label="Borrar búsqueda" onClick={() => setQuery('')}>
                    <X size={15} aria-hidden="true" />
                  </button>
                )}
              </label>
              <span className="pgx-table__count" aria-live="polite">{shown.length} {shown.length === 1 ? 'cuenta' : 'cuentas'}</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th><span className="pgx-th">Persona</span></th>
                  <th><span className="pgx-th">Rol</span></th>
                  <th className="pgx-wide"><span className="pgx-th">Servicio</span></th>
                  <th className="pgx-chev"><span className="pgx-sr">Detalle</span></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((u) => {
                  const isOpen = openId === u.id;
                  const detailId = `adm-user-${u.id}`;
                  const locked = roleOf(u) === 'ADMIN' || u.id === me?.id;
                  return (
                    <Fragment key={u.id}>
                      <tr className={isOpen ? 'pgx-row is-open' : 'pgx-row'} onClick={() => setOpenId(isOpen ? null : u.id)}>
                        <td>
                          <button type="button" className="pgx-row__name" aria-expanded={isOpen} aria-controls={isOpen ? detailId : undefined}
                            onClick={(e) => { e.stopPropagation(); setOpenId(isOpen ? null : u.id); }}>{nameOf(u)}</button>
                          <span className="adm-email">{u.email}</span>
                        </td>
                        <td>{ROLE_LABEL[roleOf(u)] ?? roleOf(u)}</td>
                        <td className="pgx-wide">{SERVICE_LABEL[u.service_status] ?? u.service_status}</td>
                        <td className="pgx-chev"><ChevronDown size={16} aria-hidden="true" /></td>
                      </tr>
                      {isOpen && (
                        <tr className="pgx-row-detail">
                          <td colSpan={4}>
                            <div className="adm-detail" id={detailId}>
                              <dl>
                                <div><dt>Alta</dt><dd>{day(u.date_joined)}</dd></div>
                                <div><dt>Último ingreso</dt><dd>{day(u.last_login)}</dd></div>
                                <div><dt>Servicio</dt><dd>{SERVICE_LABEL[u.service_status] ?? u.service_status}</dd></div>
                              </dl>
                              {locked
                                ? <p className="adm-muted">{u.id === me?.id ? 'Es tu cuenta.' : 'El rol de un administrador no se cambia desde aquí.'}</p>
                                : <RoleForm user={u} onSaved={saved} />}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {!shown.length && <tr className="pgx-none"><td colSpan={4}>Ninguna cuenta coincide.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AdminShell>
  );
};

export default AdminUsers;
