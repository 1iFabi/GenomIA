import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import AdminShell from './AdminShell';
import { STAGE_NAMES, describeEvent, formatWhen } from './activityText';

const FIGURES = [
  ['clients', 'Clientes'],
  ['purchases_pending', 'Compras sin pagar'],
  ['services_open', 'Servicios en curso'],
  ['services_completed', 'Informes listos'],
];
const STAFF = [['ADMIN', 'Administradores'], ['ANALISTA', 'Analistas'], ['RECEPCION', 'Recepción']];
const LATEST = 5;

const Skel = ({ width }) => <span className="pgx-skel" style={{ '--w': width }} />;

const Loading = () => (
  <section role="status" aria-live="polite" aria-busy="true">
    <span className="pgx-sr">Cargando el resumen…</span>
    <dl className="adm-figures" aria-hidden="true">
      {FIGURES.map(([key, label]) => <div key={key} className="adm-figure"><dt>{label}</dt><dd><Skel width="3rem" /></dd></div>)}
    </dl>
    <div className="adm-sheet" aria-hidden="true"><Skel width="40%" /><Skel width="90%" /><Skel width="70%" /></div>
  </section>
);

const days = (n) => (n === 0 ? 'de hoy' : n === 1 ? 'hace 1 día' : `hace ${n} días`);

const AdminOverview = () => {
  const [state, setState] = useState({ status: 'loading' });

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    const [summary, activity] = await Promise.all([
      apiRequest(API_ENDPOINTS.ADMIN_OVERVIEW, { method: 'GET' }),
      apiRequest(API_ENDPOINTS.ADMIN_ACTIVITY, { method: 'GET' }),
    ]);
    if (!summary.ok) {
      setState({ status: 'error' });
      return;
    }
    setState({ status: 'ready', data: summary.data, events: activity.ok ? activity.data.events.slice(0, LATEST) : null });
  }, []);

  useEffect(() => { load(); }, [load]);

  const { status, data, events } = state;
  const busiest = data ? Math.max(1, ...data.stages.map((s) => s.count)) : 1;

  return (
    <AdminShell section="admin_overview" lede="El estado del servicio, el personal y lo último que pasó con los datos.">
      {status === 'loading' && <Loading />}
      {status === 'error' && (
        <div className="pgx-status">
          <p role="alert">No se pudo cargar el resumen.</p>
          <button type="button" className="pgx-retry" onClick={load}>Reintentar</button>
        </div>
      )}
      {status === 'ready' && (
        <>
          <dl className="adm-figures">
            {FIGURES.map(([key, label]) => (
              <div key={key} className="adm-figure"><dt>{label}</dt><dd>{data[key].toLocaleString('es-CL')}</dd></div>
            ))}
          </dl>

          <section className="adm-sheet" aria-labelledby="adm-stages">
            <div className="adm-sheet__head"><h2 id="adm-stages">Servicios por etapa</h2></div>
            <ol className="adm-stages">
              {data.stages.map((s) => (
                <li key={s.code} className="adm-stage" style={{ '--share': s.count / busiest }}>
                  <i aria-hidden="true" />
                  <b>{s.count}</b>
                  <span className="adm-stage__name">{STAGE_NAMES[s.code] ?? s.code}</span>
                  {s.oldest_days !== null && s.count > 0 && <span>El más antiguo, {days(s.oldest_days)}</span>}
                </li>
              ))}
            </ol>
          </section>

          <section className="adm-sheet" aria-labelledby="adm-staff">
            <div className="adm-sheet__head">
              <h2 id="adm-staff">Personal</h2>
              <Link to="/dashboard/admin/usuarios">Gestionar roles</Link>
            </div>
            <ul className="adm-staff">
              {STAFF.map(([code, label]) => (
                <li key={code}>
                  <Link className="adm-chip" to={`/dashboard/admin/usuarios?rol=${code}`}>{label} <b>{data.staff[code] ?? 0}</b></Link>
                </li>
              ))}
            </ul>
          </section>

          <section className="adm-sheet" aria-labelledby="adm-latest">
            <div className="adm-sheet__head">
              <h2 id="adm-latest">Últimos movimientos</h2>
              <Link to="/dashboard/admin/actividad">Ver toda la actividad</Link>
            </div>
            {events === null && <p className="adm-muted">No se pudo cargar la actividad.</p>}
            {events?.length === 0 && <p className="adm-muted">Aún no hay actividad registrada.</p>}
            {events?.length > 0 && (
              <ul className="adm-feed">
                {events.map((e) => (
                  <li key={e.id}>
                    <span className="adm-who">
                      <b>{e.actor.name}</b>
                      <span>{describeEvent(e)}{e.subject && e.subject.id !== e.actor.id ? ` · ${e.subject.name}` : ''}</span>
                    </span>
                    <time className="adm-muted" dateTime={e.at}>{formatWhen(e.at)}</time>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </AdminShell>
  );
};

export default AdminOverview;
