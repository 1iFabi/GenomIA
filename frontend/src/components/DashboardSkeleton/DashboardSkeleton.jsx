import React from 'react';
import { RESULT_MODULES, SLOT_KEY } from '../../config/resultNav';
import { RasgosPageSkeleton } from '../../pages/Rasgos/RasgosLoading';
import { FarmacoPageSkeleton } from '../../pages/Farmacogenetica/FarmacoLoading';
import ContinentDeckSkeleton from '../ContinentExplorer/ContinentDeckSkeleton';
import '../ContinentExplorer/ContinentExplorer.css';
import './DashboardSkeleton.css';

const getDashboardRole = (user) => {
  const roles = Array.isArray(user?.roles) ? user.roles : [];

  if (user?.is_admin || user?.is_staff || roles.includes('ADMIN')) return 'admin';
  if (user?.is_analyst || roles.includes('ANALISTA')) return 'analyst';
  if (user?.is_reception || roles.includes('RECEPCION')) return 'reception';
  return 'user';
};

export const SkeletonBlock = ({ className = '', ...props }) => (
  <span
    {...props}
    className={`dashboard-skeleton__block ${className}`.trim()}
    aria-hidden="true"
  />
);

export const DashboardPageSkeleton = ({
  children,
  className = '',
  label = 'Cargando contenido del panel',
}) => (
  <section
    className={`dashboard-page-skeleton ${className}`.trim()}
    role="status"
    aria-live="polite"
    aria-atomic="true"
    aria-busy="true"
  >
    <span className="dashboard-skeleton__announcement">{label}</span>
    <div className="dashboard-page-skeleton__content" aria-hidden="true">
      {children}
    </div>
  </section>
);

const GUIDE_COLOURS = { ink: '#0f2341', tint: '#e3ecfa' };
const range = (n) => Array.from({ length: n }, (_, i) => i);

// The stretch of the helix the client last looked at (the dashboard reopens on it).
const savedModule = () => {
  try {
    const n = Number(sessionStorage.getItem(SLOT_KEY));
    return RESULT_MODULES[Number.isInteger(n) && n >= 0 && n < RESULT_MODULES.length ? n : 0];
  } catch {
    return RESULT_MODULES[0];
  }
};

const Announce = ({ children }) => <span className="dashboard-skeleton__announcement">{children}</span>;

/**
 * The client dashboard while it loads: the same stage, already in the module's pastel, the
 * greeting bar with the menu disc, and the words column (title, line, way in, the five modules
 * with their coloured dots). The helix fades in on its own when its frames arrive.
 */
const ClientStageSkeleton = () => {
  const module = savedModule();
  return (
    <div className="cskel-stage" style={{ '--tint': module.tint, '--ink': module.ink }} role="status" aria-live="polite" aria-busy="true">
      <Announce>Cargando tu ADN</Announce>
      <div className="cskel-stage__bar" aria-hidden="true">
        <SkeletonBlock className="cskel-hello" />
        <span className="cskel-disc" />
      </div>
      <span className="cskel-stage__helix" aria-hidden="true" />
      <div className="cskel-stage__copy" aria-hidden="true">
        <SkeletonBlock className="cskel-title" />
        <SkeletonBlock className="cskel-title cskel-title--short" />
        <SkeletonBlock className="cskel-line" />
        <SkeletonBlock className="cskel-enter" />
        <ul className="cskel-mods">
          {RESULT_MODULES.map((m) => (
            <li key={m.key} className="cskel-mod" style={{ '--dot': m.rung }}><SkeletonBlock /></li>
          ))}
        </ul>
      </div>
    </div>
  );
};

const PAGE_MODULE = { ancestria: 0, farmacogenetica: 1, rasgos: 2, enfermedades: 3 };

/**
 * Ancestría's own frame, not a generic one, on its lilac: the same paddings, the hero's title and line, the map box
 * at its real height with the globe's circle sized the way TacticalGlobe3D sizes it, and the continent rail
 * drawn with ContinentExplorer's loading markup, so the globe and the cards land exactly on their skeletons.
 */
const AncestriaFrame = () => (
  <>
    <span className="askel__space" aria-hidden="true" />
    <div className="askel__page" aria-hidden="true">
      <div className="askel__head">
        <SkeletonBlock className="askel__title" />
        <span className="askel__lede"><SkeletonBlock /><SkeletonBlock /></span>
      </div>
      <div className="askel__card">
        <div className="askel__stage">
          <SkeletonBlock className="cskel-globe" />
          <span className="askel__mark" />
          <div className="askel__status">
            <SkeletonBlock className="askel__status-heading" />
            {range(3).map((i) => (
              <div className="askel__status-row" key={i}><SkeletonBlock /><SkeletonBlock /><SkeletonBlock /></div>
            ))}
          </div>
          <span className="askel__expand" />
        </div>
        <div className="askel__rail">
          <div className="cx cx--fit cx--loading">
            <SkeletonBlock className="cx-skeleton__title" />
            <SkeletonBlock className="cx-skeleton__lede" />
            <div className="cx-continents">
              {range(4).map((i) => (
                <div key={i} className="cx-card cx-card--skeleton">
                  <SkeletonBlock className="cx-card__shape cx-skeleton__shape" />
                  <SkeletonBlock className="cx-skeleton__name" />
                  <SkeletonBlock className="cx-skeleton__value" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
    <span className="askel__handle" aria-hidden="true"><SkeletonBlock /><SkeletonBlock /></span>
    {/* The phone (≤860px, Ancestria.jsx's PHONE_MAX): the globe on the lilac and the continent deck under it. */}
    <div className="askel__phone" aria-hidden="true">
      <div className="askel__phone-globe"><SkeletonBlock className="cskel-globe" /></div>
      <ContinentDeckSkeleton />
    </div>
  </>
);

const ClientPageBody = ({ page }) => {
  if (page === 'enfermedades') {
    return (
      <div className="cskel-panels cskel-panels--two">
        {range(2).map((i) => (
          <div className="cskel-panel" key={i}>
            <SkeletonBlock className="cskel-h2" />
            {range(3).map((r) => <div className="cskel-pair" key={r}><SkeletonBlock /><SkeletonBlock /></div>)}
          </div>
        ))}
      </div>
    );
  }
  // the module guide
  return (
    <div className="cskel-panels">
      {range(3).map((i) => (
        <div className="cskel-panel" key={i}>
          <SkeletonBlock className="cskel-h2" />
          <SkeletonBlock className="cskel-line" />
          <SkeletonBlock className="cskel-line cskel-line--short" />
        </div>
      ))}
    </div>
  );
};

/**
 * A result page while it loads: the module bar exactly where it will be (back disc, the strand of
 * five dots with this module named, menu disc), the page title, and the shape of this page's content.
 */
export const ClientPageSkeleton = ({ page }) => {
  // Rasgos and Farmacogenética draw the very skeleton their page shows while results load, so the two never swap.
  if (page === 'rasgos') return <RasgosPageSkeleton />;
  if (page === 'farmacogenetica') return <FarmacoPageSkeleton />;
  const module = RESULT_MODULES[PAGE_MODULE[page]];
  const colours = module || GUIDE_COLOURS;
  return (
    <div className={`cskel-page${page === 'ancestria' ? ' askel' : ''}`} data-page={page} style={{ '--tint': colours.tint, '--ink': colours.ink }} role="status" aria-live="polite" aria-busy="true">
      <Announce>{module ? `Cargando ${module.name}` : 'Cargando la guía de módulos'}</Announce>
      <div className="cskel-bar" aria-hidden="true">
        <span className="cskel-disc" />
        <span className="cskel-strand">
          {RESULT_MODULES.map((m, i) => (
            <span key={m.key} className="cskel-strand__dot" style={{ '--dot': m.rung }} data-active={i === PAGE_MODULE[page] ? '' : undefined} />
          ))}
        </span>
        <span className="cskel-disc" />
      </div>
      {page === 'ancestria' ? <AncestriaFrame /> : (
        <div className="cskel-page__content" aria-hidden="true">
          <div className="cskel-head">
            <SkeletonBlock className="cskel-head__title" />
            <SkeletonBlock className="cskel-line" />
          </div>
          <ClientPageBody page={page} />
        </div>
      )}
    </div>
  );
};

const OverviewDashboardSkeleton = ({ variant }) => (
  <div className={`dashboard-skeleton__overview dashboard-skeleton__overview--${variant}`}>
    <div className="dashboard-skeleton__stat-grid">
      {Array.from({ length: 3 }, (_, index) => (
        <div className="dashboard-skeleton__stat-card" key={index}>
          <SkeletonBlock className="dashboard-skeleton__stat-label" />
          <SkeletonBlock className="dashboard-skeleton__stat-value" />
        </div>
      ))}
    </div>
    {variant === 'admin' && (
      <div className="dashboard-skeleton__admin-card">
        <SkeletonBlock className="dashboard-skeleton__panel-title" />
        <SkeletonBlock className="dashboard-skeleton__neutral-line" />
        <SkeletonBlock className="dashboard-skeleton__neutral-line dashboard-skeleton__neutral-line--short" />
        <SkeletonBlock className="dashboard-skeleton__result-action" />
      </div>
    )}
  </div>
);

const ReceptionDashboardSkeleton = () => (
  <div className="dashboard-skeleton__reception">
    <div className="dashboard-skeleton__search-panel">
      <SkeletonBlock className="dashboard-skeleton__panel-title" />
      <SkeletonBlock className="dashboard-skeleton__neutral-line" />
      <SkeletonBlock className="dashboard-skeleton__search-field" />
      <SkeletonBlock className="dashboard-skeleton__search-action" />
    </div>
  </div>
);

const CLIENT_PAGES = ['ancestria', 'farmacogenetica', 'enfermedades', 'modulos', 'rasgos'];

const dashboardPages = {
  rasgos: 'rasgos',
  ancestria: 'ancestria',
  farmacogenetica: 'farmacogenetica',
  enfermedades: 'enfermedades',
  modulos: 'modulos',
  'admin/analysts': 'analysts',
};

// Staff access list (/dashboard/admin/analysts); every result page uses ClientPageSkeleton.
const DashboardReportSkeleton = () => (
  <div className="dashboard-skeleton__report">
    <div className="dashboard-skeleton__report-toolbar">
      <SkeletonBlock className="dashboard-skeleton__search-field" />
      <SkeletonBlock className="dashboard-skeleton__search-action" />
    </div>
    <div className="dashboard-skeleton__report-panel">
      <SkeletonBlock className="dashboard-skeleton__panel-title" />
      {Array.from({ length: 5 }, (_, index) => (
        <div className="dashboard-skeleton__table-row dashboard-skeleton__table-row--access" key={index}>
          <SkeletonBlock /><SkeletonBlock /><SkeletonBlock /><SkeletonBlock />
        </div>
      ))}
    </div>
  </div>
);

const DashboardSkeleton = ({ variant = 'neutral', pathname = '/dashboard' }) => {
  const route = pathname.replace(/^\/dashboard\/?/, '').replace(/\/+$/, '');
  const page = dashboardPages[route] ?? 'overview';
  const pageLabel = page === 'overview' ? 'panel' : page === 'analysts' ? 'usuarios' : route;
  const resolvedVariant = ['neutral', 'user', 'admin', 'analyst', 'reception'].includes(variant)
    ? variant
    : 'neutral';

  // Clients are almost everyone who opens /dashboard: while the session is still unknown, show their stage.
  if (page === 'overview' && (resolvedVariant === 'neutral' || resolvedVariant === 'user')) return <ClientStageSkeleton />;
  // Result pages look the same for every role.
  if (CLIENT_PAGES.includes(page)) return <ClientPageSkeleton page={page} />;

  return (
    <div
      className="dashboard-skeleton"
      data-variant={resolvedVariant}
      data-page={page}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="dashboard-skeleton__announcement">Cargando {pageLabel}</span>

      <aside className="dashboard-skeleton__sidebar" aria-hidden="true">
        <span className="dashboard-skeleton__sidebar-brand" />
        <div className="dashboard-skeleton__sidebar-nav">
          <span className="dashboard-skeleton__sidebar-item" />
          <span className="dashboard-skeleton__sidebar-item" />
          <span className="dashboard-skeleton__sidebar-item" />
        </div>
        <div className="dashboard-skeleton__sidebar-footer">
          <span className="dashboard-skeleton__sidebar-item" />
          <span className="dashboard-skeleton__sidebar-item" />
        </div>
      </aside>

      <span className="dashboard-skeleton__menu" aria-hidden="true" />

      <main className="dashboard-skeleton__main" aria-hidden="true">
        <header className="dashboard-skeleton__header">
          <div className="dashboard-skeleton__headline">
            <SkeletonBlock className="dashboard-skeleton__welcome" />
            <div className="dashboard-skeleton__subtitle">
              <SkeletonBlock />
              <SkeletonBlock />
            </div>
          </div>
        </header>

        <section className={`dashboard-skeleton__content dashboard-skeleton__content--${resolvedVariant}`}>
          {page === 'analysts' && <DashboardReportSkeleton />}
          {page === 'overview' && (resolvedVariant === 'admin' || resolvedVariant === 'analyst') && (
            <OverviewDashboardSkeleton variant={resolvedVariant} />
          )}
          {page === 'overview' && resolvedVariant === 'reception' && <ReceptionDashboardSkeleton />}
        </section>
      </main>
    </div>
  );
};

DashboardSkeleton.getRoleVariant = getDashboardRole;

export default DashboardSkeleton;
