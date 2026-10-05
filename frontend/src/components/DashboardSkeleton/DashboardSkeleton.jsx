import React from 'react';
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
  label = 'Loading dashboard content',
}) => (
  <section
    className={`dashboard-page-skeleton ${className}`.trim()}
    role="status"
    aria-live="polite"
    aria-atomic="true"
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
      {Array.from({ length: variant === 'analyst' ? 3 : 4 }, (_, index) => (
        <div className="dashboard-skeleton__stat-card" key={index}>
          <SkeletonBlock className="dashboard-skeleton__stat-label" />
          <SkeletonBlock className="dashboard-skeleton__stat-value" />
          <SkeletonBlock className="dashboard-skeleton__stat-note" />
        </div>
      ))}
    </div>
    {variant === 'analyst' ? (
      <div className="dashboard-skeleton__table-panel">
        <SkeletonBlock className="dashboard-skeleton__panel-title" />
        {Array.from({ length: 5 }, (_, index) => (
          <div className="dashboard-skeleton__table-row" key={index}>
            <SkeletonBlock />
            <SkeletonBlock />
            <SkeletonBlock />
          </div>
        ))}
      </div>
    ) : (
      <div className="dashboard-skeleton__chart-panel">
        <SkeletonBlock className="dashboard-skeleton__panel-title" />
        <div className="dashboard-skeleton__chart-bars">
          {Array.from({ length: 8 }, (_, index) => (
            <SkeletonBlock className={`dashboard-skeleton__chart-bar dashboard-skeleton__chart-bar--${index + 1}`} key={index} />
          ))}
        </div>
      </div>
    )}
  </div>
);

const ReceptionDashboardSkeleton = () => (
  <div className="dashboard-skeleton__reception">
    <div className="dashboard-skeleton__search-panel">
      <SkeletonBlock className="dashboard-skeleton__panel-title" />
      <SkeletonBlock className="dashboard-skeleton__search-field" />
      <SkeletonBlock className="dashboard-skeleton__search-action" />
    </div>
    <div className="dashboard-skeleton__results-panel">
      <SkeletonBlock className="dashboard-skeleton__panel-title" />
      {Array.from({ length: 4 }, (_, index) => (
        <div className="dashboard-skeleton__result-row" key={index}>
          <SkeletonBlock className="dashboard-skeleton__result-avatar" />
          <div className="dashboard-skeleton__result-copy">
            <SkeletonBlock />
            <SkeletonBlock />
          </div>
          <SkeletonBlock className="dashboard-skeleton__result-action" />
        </div>
      ))}
    </div>
  </div>
);

const NeutralDashboardSkeleton = () => (
  <div className="dashboard-skeleton__neutral">
    <div className="dashboard-skeleton__neutral-panel">
      <SkeletonBlock className="dashboard-skeleton__panel-title" />
      <SkeletonBlock className="dashboard-skeleton__neutral-line" />
      <SkeletonBlock className="dashboard-skeleton__neutral-line dashboard-skeleton__neutral-line--short" />
    </div>
    <div className="dashboard-skeleton__neutral-cards">
      {Array.from({ length: 3 }, (_, index) => (
        <div className="dashboard-skeleton__neutral-card" key={index}>
          <SkeletonBlock className="dashboard-skeleton__neutral-line" />
          <SkeletonBlock className="dashboard-skeleton__neutral-line dashboard-skeleton__neutral-line--short" />
        </div>
      ))}
    </div>
  </div>
);

const DashboardSkeleton = ({ variant = 'neutral' }) => {
  const resolvedVariant = ['neutral', 'user', 'admin', 'analyst', 'reception'].includes(variant)
    ? variant
    : 'neutral';

  return (
    <div
      className="dashboard-skeleton"
      data-variant={resolvedVariant}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="dashboard-skeleton__announcement">Loading dashboard</span>

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
          <SkeletonBlock className="dashboard-skeleton__action" />
        </header>

        <section className={`dashboard-skeleton__content dashboard-skeleton__content--${resolvedVariant}`}>
          {resolvedVariant === 'neutral' && <NeutralDashboardSkeleton />}
          {resolvedVariant === 'user' && <UserDashboardSkeleton />}
          {(resolvedVariant === 'admin' || resolvedVariant === 'analyst') && (
            <OverviewDashboardSkeleton variant={resolvedVariant} />
          )}
          {resolvedVariant === 'reception' && <ReceptionDashboardSkeleton />}
        </section>
      </main>
    </div>
  );
};

DashboardSkeleton.getRoleVariant = getDashboardRole;

export default DashboardSkeleton;
