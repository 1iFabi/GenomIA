import React from 'react';
import Loader from '../Loader/Loader';
import './DashboardSkeleton.css';

const skeletonCards = [
  'ancestria',
  'rasgos',
  'farmacogenetica',
  'enfermedades',
];

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

const UserDashboardSkeleton = () => (
  <div className="dashboard-skeleton__card-grid">
    {skeletonCards.map((card) => (
      <div
        className={`dashboard-skeleton__card dashboard-skeleton__card--${card}`}
        key={card}
      >
        <SkeletonBlock className="dashboard-skeleton__card-eyebrow" />
        <div className="dashboard-skeleton__card-content">
          <SkeletonBlock className="dashboard-skeleton__card-title" />
          <SkeletonBlock className="dashboard-skeleton__card-line" />
          <SkeletonBlock className="dashboard-skeleton__card-line dashboard-skeleton__card-line--short" />
          <SkeletonBlock className="dashboard-skeleton__card-cta" />
        </div>
      </div>
    ))}
  </div>
);

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

const dashboardPages = {
  ancestria: 'ancestria',
  farmacogenetica: 'farmacogenetica',
  enfermedades: 'enfermedades',
  modulos: 'modulos',
  'admin/analysts': 'analysts',
};

const DashboardReportSkeleton = ({ page }) => {
  if (page === 'analysts') {
    return (
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
  }

  if (page === 'ancestria') {
    return (
      <div className="dashboard-skeleton__report">
        <div className="dashboard-skeleton__map-panel">
          <div className="dashboard-skeleton__map-foot">
            <SkeletonBlock className="dashboard-skeleton__panel-title" />
            <SkeletonBlock className="dashboard-skeleton__neutral-line" />
          </div>
        </div>
        <div className="dashboard-skeleton__report-panel"><SkeletonBlock className="dashboard-skeleton__panel-title" /><SkeletonBlock className="dashboard-skeleton__neutral-line" /></div>
      </div>
    );
  }


  if (page === 'modulos') {
    return (
      <div className="dashboard-skeleton__module-grid">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="dashboard-skeleton__report-panel" key={index}>
            <SkeletonBlock className="dashboard-skeleton__panel-title" />
            <SkeletonBlock className="dashboard-skeleton__neutral-line" />
            <SkeletonBlock className="dashboard-skeleton__neutral-line dashboard-skeleton__neutral-line--short" />
            <div className="dashboard-skeleton__table-row"><SkeletonBlock /><SkeletonBlock /><SkeletonBlock /></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={`dashboard-skeleton__report ${page === 'enfermedades' ? 'dashboard-skeleton__report--risk' : ''}`}>
      {Array.from({ length: page === 'enfermedades' ? 2 : 1 }, (_, panel) => (
        <div className="dashboard-skeleton__report-panel" key={panel}>
          <SkeletonBlock className="dashboard-skeleton__panel-title" />
          {Array.from({ length: 4 }, (_, row) => (
            <div className="dashboard-skeleton__table-row" key={row}>
              <SkeletonBlock /><SkeletonBlock /><SkeletonBlock />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
};

const DashboardSkeleton = ({ variant = 'neutral', pathname = '/dashboard' }) => {
  const route = pathname.replace(/^\/dashboard\/?/, '').replace(/\/+$/, '');
  const page = dashboardPages[route] ?? 'overview';
  const pageLabel = page === 'overview' ? 'panel' : page === 'analysts' ? 'usuarios' : route;
  const resolvedVariant = ['neutral', 'user', 'admin', 'analyst', 'reception'].includes(variant)
    ? variant
    : 'neutral';

  if (page === 'overview' && resolvedVariant === 'neutral') {
    return (
      <div className="dashboard-session-loading" aria-busy="true">
        <Loader label="Cargando panel…" />
      </div>
    );
  }

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
          {page === 'overview' && resolvedVariant === 'user' && <SkeletonBlock className="dashboard-skeleton__action" />}
        </header>

        <section className={`dashboard-skeleton__content dashboard-skeleton__content--${resolvedVariant}`}>
          {page !== 'overview' && <DashboardReportSkeleton page={page} />}
          {page === 'overview' && resolvedVariant === 'user' && <UserDashboardSkeleton />}
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
