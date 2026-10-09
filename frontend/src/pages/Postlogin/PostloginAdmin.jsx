import React, { useMemo, useState, useEffect, useRef } from 'react';
import { Menu, X, Users, FileText, Activity } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { clearToken } from '../../config/api';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import { useAdminStats } from '../../hooks/useAdminStats';
import { SkeletonBlock } from '../../components/DashboardSkeleton/DashboardSkeleton';
import './PostloginAdmin.css';

const PostloginAdmin = ({ user, mode = 'admin' }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const { stats, loading } = useAdminStats();
  const statsLoaded = useRef(false);
  const showStatsSkeleton = loading && !statsLoaded.current;

  useEffect(() => {
    if (!loading) statsLoaded.current = true;
  }, [loading]);
  const isAdmin = mode === 'admin';

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) {
        setIsMobileMenuOpen(false);
      }
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleLogout = async () => {
    try {
      await clearToken();
    } catch (error) {
      console.error('Error al cerrar sesion', error);
    }
    navigate('/');
  };

  const displayName = useMemo(() => {
    const candidates = [
      user?.first_name,
      user?.firstName,
      user?.name,
      user?.username,
      user?.email
    ];
    return candidates.find(Boolean) || 'Usuario';
  }, [user]);

  return (
    <div className="postlogin-admin">
      {isMobile && (
        <button 
          className="postlogin-admin__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      )}

      <aside className="postlogin-admin__sidebar">
        <AdminSidebar 
          onLogout={handleLogout} 
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
          isAdmin={isAdmin}
        />
      </aside>

      <main className="postlogin-admin__main">
        <header className="postlogin-admin__header">
          {isAdmin && (
            <div className="postlogin-admin__badge">
              ADMINISTRADOR
            </div>
          )}
          <div className="postlogin-admin__headline">

            <h1 className="postlogin-admin__title">
              Bienvenido/a {displayName}!
            </h1>
            <p className="postlogin-admin__subtitle">
              Esta es la vista {isAdmin ? 'del administrador' : 'del analista'}, donde podrás gestionar usuarios y explorar la base de datos del sistema, que integra genotipos y fenotipos.
            </p>
          </div>
        </header>

        <section className="postlogin-admin__stats" aria-label="Estadísticas">
          {showStatsSkeleton && (
            <span className="dashboard-skeleton__announcement" role="status">
              Cargando estadísticas…
            </span>
          )}
          <div className="postlogin-admin__stats-grid">
            <div className="postlogin-admin__stat-card">
              <div className="postlogin-admin__stat-header">
                <span className="postlogin-admin__stat-label">Usuarios Totales</span>
                <Users size={24} className="postlogin-admin__stat-icon" style={{ color: '#0b7ad0' }} />
              </div>
              <div className="postlogin-admin__stat-value">
                {showStatsSkeleton ? <SkeletonBlock className="postlogin-admin__stat-placeholder" /> : stats.totalUsers.toLocaleString()}
              </div>
            </div>

            <div className="postlogin-admin__stat-card">
              <div className="postlogin-admin__stat-header">
                <span className="postlogin-admin__stat-label">Reportes Pendientes</span>
                <FileText size={24} className="postlogin-admin__stat-icon" style={{ color: '#f97316' }} />
              </div>
              <div className="postlogin-admin__stat-value">
                {showStatsSkeleton ? <SkeletonBlock className="postlogin-admin__stat-placeholder" /> : stats.pendingReports.toLocaleString()}
              </div>
            </div>

            <div className="postlogin-admin__stat-card">
              <div className="postlogin-admin__stat-header">
                <span className="postlogin-admin__stat-label">Análisis Completados</span>
                <Activity size={24} className="postlogin-admin__stat-icon" style={{ color: '#10b981' }} />
              </div>
              <div className="postlogin-admin__stat-value">
                {showStatsSkeleton ? <SkeletonBlock className="postlogin-admin__stat-placeholder" /> : stats.completedAnalysis.toLocaleString()}
              </div>
            </div>
          </div>
        </section>

        <section className="postlogin-admin__grid" aria-label="Administración">
          <div className="postlogin-admin__grid-wrapper">
            {isAdmin && (
              <div className="postlogin-admin__card postlogin-admin__card--blue" role="button" tabIndex="0">
                <div className="postlogin-admin__card-content">
                  <h2 className="postlogin-admin__card-title">Administración de Roles y Accesos</h2>
                  <p className="postlogin-admin__card-description">
                    Asigna o revoca acceso al rol y vista de Analista para las cuentas específicas que tú elijas.
                  </p>
                  <a
                    onClick={(e) => {
                      e.preventDefault();
                      navigate('/dashboard/admin/analysts');
                    }}
                    href="#"
                    className="postlogin-admin__card-link"
                  >
                    Gestionar permisos
                  </a>
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
};

export default PostloginAdmin;
