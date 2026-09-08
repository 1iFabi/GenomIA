import React, { useMemo, useState, useEffect } from 'react';
import { Menu, X, Users, FileText, Database, Activity } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import { useAdminStats } from '../../hooks/useAdminStats';
import './PostloginAnalyst.css'; // Use the new CSS file

const PostloginAnalyst = ({ user }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const { stats } = useAdminStats();
  const isAdmin = false; // Hardcoded for analyst

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
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (error) {
      console.error('Error al cerrar sesion', error);
    }
    clearToken();
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
    <div className="postlogin-analyst">
      {isMobile && (
        <button 
          className="postlogin-analyst__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      )}

      <aside className="postlogin-analyst__sidebar">
        <AdminSidebar 
          onLogout={handleLogout} 
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
          isAdmin={isAdmin}
        />
      </aside>

      <main className="postlogin-analyst__main">
        <header className="postlogin-analyst__header">
          <div className="postlogin-analyst__headline">
            <h1 className="postlogin-analyst__title">
              Bienvenido/a {displayName}!
            </h1>
            <p className="postlogin-analyst__subtitle">
              Esta es la vista del analista, donde podrás gestionar usuarios y explorar la base de datos del sistema, que integra genotipos y fenotipos.
            </p>
          </div>
        </header>

        <section className="postlogin-analyst__stats" aria-label="Estadísticas">
          <div className="postlogin-analyst__stats-grid">
            <div className="postlogin-analyst__stat-card">
              <div className="postlogin-analyst__stat-header">
                <span className="postlogin-analyst__stat-label">Usuarios Totales</span>
                <Users size={24} className="postlogin-analyst__stat-icon" style={{ color: '#0b7ad0' }} />
              </div>
              <div className="postlogin-analyst__stat-value">{stats.totalUsers.toLocaleString()}</div>
            </div>

            <div className="postlogin-analyst__stat-card">
              <div className="postlogin-analyst__stat-header">
                <span className="postlogin-analyst__stat-label">Reportes Pendientes</span>
                <FileText size={24} className="postlogin-analyst__stat-icon" style={{ color: '#f97316' }} />
              </div>
              <div className="postlogin-analyst__stat-value">{stats.pendingReports.toLocaleString()}</div>
            </div>

            <div className="postlogin-analyst__stat-card">
              <div className="postlogin-analyst__stat-header">
                <span className="postlogin-analyst__stat-label">Variantes en BD</span>
                <Database size={24} className="postlogin-analyst__stat-icon" style={{ color: '#8b5cf6' }} />
              </div>
              <div className="postlogin-analyst__stat-value">{stats.variantsInDB.toLocaleString()}</div>
            </div>

            <div className="postlogin-analyst__stat-card">
              <div className="postlogin-analyst__stat-header">
                <span className="postlogin-analyst__stat-label">Análisis Completados</span>
                <Activity size={24} className="postlogin-analyst__stat-icon" style={{ color: '#10b981' }} />
              </div>
              <div className="postlogin-analyst__stat-value">{stats.completedAnalysis.toLocaleString()}</div>
            </div>
          </div>
        </section>

        <section className="postlogin-analyst__grid" aria-label="Administración">
          <div className="postlogin-analyst__grid-wrapper">
            {/* Card Naranja */}
            <div className="postlogin-analyst__card postlogin-analyst__card--orange" role="button" tabIndex="0">
              <div className="postlogin-analyst__card-content">
                <h2 className="postlogin-analyst__card-title">Administrar reportes genéticos</h2>
                <p className="postlogin-analyst__card-description">
                  Gestiona los archivos genéticos de los usuarios: carga, edita o elimina sus variantes (RSIDs).
                </p>
                <a
                  onClick={(e) => {
                    e.preventDefault();
                    navigate('/dashboard/admin/reports');
                  }}
                  href="#"
                  className="postlogin-analyst__card-link"
                >
                  Administrar archivo
                </a>
              </div>
            </div>

            {/* Card Morada */}
            <div className="postlogin-analyst__card postlogin-analyst__card--purple" role="button" tabIndex="0">
              <div className="postlogin-analyst__card-content">
                <h2 className="postlogin-analyst__card-title">Base de datos de variantes genéticas</h2>
                <p className="postlogin-analyst__card-description">
                  Explora y gestiona las variantes genéticas almacenadas en la base de datos del sistema.
                </p>
                <a
                  onClick={(e) => {
                    e.preventDefault();
                    navigate('/dashboard/admin/variants');
                  }}
                  href="#"
                  className="postlogin-analyst__card-link"
                >
                  Ver variantes
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};

export default PostloginAnalyst;