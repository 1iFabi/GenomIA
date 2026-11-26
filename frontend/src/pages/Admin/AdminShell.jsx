import React from 'react';
import { useNavigate } from 'react-router-dom';
import { clearToken } from '../../config/api';
import { ADMIN_ROLE_LABEL, ADMIN_SECTIONS } from '../../config/adminNav';
import { useSession } from '../../hooks/useSession';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import '../Farmacogenetica/Farmacogenetica.css';
import './Admin.css';

/**
 * One admin page laid out like a result module: the module bar with the admin's sections, the
 * section's title, its sheets and the small closing note. Colours come from the section (adminNav).
 */
const AdminShell = ({ section, lede, children }) => {
  const { user } = useSession();
  const navigate = useNavigate();
  const page = ADMIN_SECTIONS.find((s) => s.key === section) ?? ADMIN_SECTIONS[0];

  const handleLogout = async () => {
    await clearToken();
    navigate('/');
  };

  return (
    <div className="adm-layout" style={{ '--ink': page.ink, '--tint': page.tint, '--rung': page.rung }}>
      <main className="adm-main">
        <ResultsBar user={user} onLogout={handleLogout} modules={ADMIN_SECTIONS} back={false} accountRole={ADMIN_ROLE_LABEL} />
        <div className="pgx adm">
          <header className="pgx-hero">
            <ModuleTitle className="pgx-title" moduleKey={page.key} title={page.title} />
            {lede && <p className="pgx-hero__lede">{lede}</p>}
          </header>
          {children}
          <footer className="pgx-foot">
            <p>Panel de administración. Los accesos a datos personales quedan registrados.</p>
          </footer>
        </div>
      </main>
    </div>
  );
};

export default AdminShell;
