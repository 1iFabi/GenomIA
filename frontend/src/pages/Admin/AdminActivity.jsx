import React, { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import AdminShell from './AdminShell';
import { describeEvent, formatWhen, outcomeText } from './activityText';

const KINDS = [['', 'Todo'], ['genetic', 'Resultados'], ['reception', 'Recepción'], ['status', 'Estados']];
const ROLE_LABEL = { CLIENTE: 'Cliente', ANALISTA: 'Analista', RECEPCION: 'Recepción', ADMIN: 'Administrador' };
const PAUSE_MS = 300;

const urlFor = ({ kind, q, before }) => {
  const params = new URLSearchParams();
  if (kind) params.set('kind', kind);
  if (q) params.set('q', q);
  if (before) params.set('before', before); // URLSearchParams encodes the '+' of the offset
  const query = params.toString();
  return query ? `${API_ENDPOINTS.ADMIN_ACTIVITY}?${query}` : API_ENDPOINTS.ADMIN_ACTIVITY;
};

const Person = ({ label, person }) => (
  <dl>
    <div><dt>{label}</dt><dd>{person.name}</dd></div>
    {person.email && <div><dt>Email</dt><dd>{person.email}</dd></div>}
    {person.role && <div><dt>Rol</dt><dd>{ROLE_LABEL[person.role] ?? person.role}</dd></div>}
    {person.sample_code && <div><dt>Sample ID</dt><dd>{person.sample_code}</dd></div>}
  </dl>
);

const AdminActivity = () => {
  const [kind, setKind] = useState('');
  const [query, setQuery] = useState('');
  const [q, setQ] = useState('');
  const [state, setState] = useState({ status: 'loading', events: [], next: null, more: false });
  const [openId, setOpenId] = useState(null);
  const latest = useRef(0);

  // Typing waits for a short pause before asking the server.
  useEffect(() => {
    const timer = setTimeout(() => setQ(query.trim()), PAUSE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(async (before) => {
    const ticket = ++latest.current;
    setState((s) => (before ? { ...s, more: true } : { status: 'loading', events: [], next: null, more: false }));
    const resp = await apiRequest(urlFor({ kind, q, before }), { method: 'GET' });
    if (ticket !== latest.current) return; // a newer filter already asked
    if (!resp.ok) {
      setState((s) => (before ? { ...s, more: false } : { status: 'error', events: [], next: null, more: false }));
      return;
    }
    setState((s) => ({
      status: 'ready',
      events: before ? [...s.events, ...resp.data.events] : resp.data.events,
      next: resp.data.next_before,
      more: false,
    }));
  }, [kind, q]);

  useEffect(() => { load(); }, [load]);

  const { status, events, next, more } = state;

  return (
    <AdminShell section="admin_activity" lede="Quién tocó qué datos: lecturas de resultados, búsquedas de recepción y cambios de estado.">
      <ul className="adm-tabs" aria-label="Filtrar por tipo">
        {KINDS.map(([code, label]) => (
          <li key={code || 'all'}>
            <button type="button" className="adm-tab" aria-pressed={kind === code} onClick={() => setKind(code)}><span>{label}</span></button>
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
        </div>
        {status === 'loading' && (
          <div className="adm-more" role="status" aria-busy="true">
            <span className="pgx-sr">Cargando actividad…</span>
            <span className="pgx-skel" style={{ '--w': '60%' }} aria-hidden="true" />
          </div>
        )}
        {status === 'error' && (
          <div className="pgx-status adm-more">
            <p role="alert">No se pudo cargar la actividad.</p>
            <button type="button" className="pgx-retry" onClick={() => load()}>Reintentar</button>
          </div>
        )}
        {status === 'ready' && (
          <table>
            <thead>
              <tr>
                <th><span className="pgx-th">Quién</span></th>
                <th><span className="pgx-th">Qué hizo</span></th>
                <th className="pgx-wide"><span className="pgx-th">Sobre quién</span></th>
                <th className="pgx-chev"><span className="pgx-sr">Detalle</span></th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => {
                const isOpen = openId === e.id;
                const detailId = `adm-event-${e.id}`;
                const toggle = () => setOpenId(isOpen ? null : e.id);
                return (
                  <Fragment key={e.id}>
                    <tr className={isOpen ? 'pgx-row is-open' : 'pgx-row'} onClick={toggle}>
                      <td>
                        <button type="button" className="pgx-row__name" aria-expanded={isOpen} aria-controls={isOpen ? detailId : undefined}
                          onClick={(ev) => { ev.stopPropagation(); toggle(); }}>{e.actor.name}</button>
                        <span className="adm-email">{ROLE_LABEL[e.actor.role] ?? ''}</span>
                      </td>
                      <td>
                        {describeEvent(e)}
                        <span className="adm-email"><time dateTime={e.at}>{formatWhen(e.at)}</time></span>
                      </td>
                      <td className="pgx-wide">{e.subject ? e.subject.name : <span className="adm-muted">Sin resultado</span>}</td>
                      <td className="pgx-chev"><ChevronDown size={16} aria-hidden="true" /></td>
                    </tr>
                    {isOpen && (
                      <tr className="pgx-row-detail">
                        <td colSpan={4}>
                          <div className="adm-detail" id={detailId}>
                            <Person label="Quién" person={e.actor} />
                            {e.subject ? <Person label="Sobre quién" person={e.subject} /> : <p className="adm-muted">La búsqueda no encontró a nadie.</p>}
                            <dl>
                              <div><dt>Cuándo</dt><dd>{formatWhen(e.at)}</dd></div>
                              {e.outcome && <div><dt>Resultado</dt><dd>{outcomeText(e.outcome)}</dd></div>}
                            </dl>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {!events.length && <tr className="pgx-none"><td colSpan={4}>{q || kind ? 'Ningún evento coincide.' : 'Aún no hay actividad registrada.'}</td></tr>}
            </tbody>
          </table>
        )}
        {status === 'ready' && next && (
          <div className="adm-more">
            <button type="button" className="pgx-retry" disabled={more} onClick={() => load(next)}>{more ? 'Cargando…' : 'Cargar más'}</button>
          </div>
        )}
      </div>
    </AdminShell>
  );
};

export default AdminActivity;
