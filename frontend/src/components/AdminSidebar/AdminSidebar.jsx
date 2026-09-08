import React, { useState, useEffect } from 'react'
import { LogOut, FileText, Database, Shield } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import './AdminSidebar.css'

const AdminSidebar = ({ onLogout, user, isMobileMenuOpen = false, setIsMobileMenuOpen = () => {}, isAdmin = false, showNavItems = true }) => {
  const navigate = useNavigate()
  const [isHovered, setIsHovered] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 1024)
      if (window.innerWidth > 1024 && setIsMobileMenuOpen) {
        setIsMobileMenuOpen(false)
      }
    }
    
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [setIsMobileMenuOpen])

  // Bloquear scroll del body cuando el menú está abierto en móviles
  useEffect(() => {
    if (!isMobile) return
    const html = document.documentElement
    const prev = html.style.overflow
    html.style.overflow = isMobileMenuOpen ? 'hidden' : prev || ''
    return () => {
      html.style.overflow = prev || ''
    }
  }, [isMobileMenuOpen, isMobile])

  const closeMenuAndNavigate = (path) => (e) => {
    e.preventDefault()
    if (isMobile) {
      setIsMobileMenuOpen(false)
    }
    navigate(path)
  }

  const isExpanded = isHovered

  return (
    <>
      {/* Overlay para cerrar el menú en móviles */}
      <div 
        className={`admin-sidebar__overlay ${isMobile && isMobileMenuOpen ? 'admin-sidebar__overlay--open' : ''}`}
        onClick={() => setIsMobileMenuOpen(false)}
        aria-hidden={!isMobileMenuOpen}
      />

      <aside 
        className={`admin-sidebar ${
          isExpanded ? 'admin-sidebar--unfolded' : 'admin-sidebar--folded'
        } ${
          isMobile && isMobileMenuOpen ? 'admin-sidebar--mobile-open' : ''
        }`}
        onMouseEnter={() => !isMobile && setIsHovered(true)}
        onMouseLeave={() => !isMobile && setIsHovered(false)}
      >
        <div className="admin-sidebar__header">
          <div className="admin-sidebar__brand" onClick={() => navigate('/dashboard')} style={{ cursor: 'pointer' }}>
            <img src="/cSolido.png" alt="GenomIA Logo" className="admin-sidebar__logo" />
            {isExpanded && !isMobile && <span className="admin-sidebar__brand-text">Genom<span className="admin-sidebar__brand-highlight">IA</span>.</span>}
          </div>
        </div>

        <nav className="admin-sidebar__nav">
          { showNavItems &&
            <>
              {/* Administrar Reportes Genéticos */}
              <a 
                href="#"
                className="admin-sidebar__nav-item"
                title={!isExpanded && !isMobile ? 'Administrar reportes genéticos' : undefined}
                onClick={closeMenuAndNavigate('/dashboard/admin/reports')}
              >
                <FileText size={20} className="admin-sidebar__nav-icon" />
                {(isExpanded || isMobile) && (
                  <span className="admin-sidebar__nav-label">Administrar reportes genéticos</span>
                )}
              </a>

              {(isExpanded || isMobile) && <div className="admin-sidebar__divider" />}

              {/* Ver Variantes en Base de Datos */}
              <a 
                href="#ver-variantes"
                className="admin-sidebar__nav-item"
                title={!isExpanded && !isMobile ? 'Ver variantes en base de datos' : undefined}
                onClick={closeMenuAndNavigate('/dashboard/admin/variants')}
              >
                <Database size={20} className="admin-sidebar__nav-icon" />
                {(isExpanded || isMobile) && (
                  <span className="admin-sidebar__nav-label">Ver variantes en base de datos</span>
                )}
              </a>

              {isAdmin && (isExpanded || isMobile) && <div className="admin-sidebar__divider" />}

              {isAdmin && (
                <a 
                  href="#gestionar-analistas"
                  className="admin-sidebar__nav-item"
                  title={!isExpanded && !isMobile ? 'Otorgar permisos' : undefined}
                  onClick={closeMenuAndNavigate('/dashboard/admin/analysts')}
                >
                  <Shield size={20} className="admin-sidebar__nav-icon" />
                  {(isExpanded || isMobile) && (
                    <span className="admin-sidebar__nav-label">Otorgar permisos</span>
                  )}
                </a>
              )}
            </>
          }
        </nav>

        <div className="admin-sidebar__footer">
          {onLogout && (
            <button 
              type="button" 
              className="admin-sidebar__logout" 
              onClick={() => {
                if (isMobile) setIsMobileMenuOpen(false)
                onLogout()
              }}
              title={!isExpanded && !isMobile ? 'Cerrar sesión' : undefined}
            >
              <LogOut size={20} />
              {(isExpanded || isMobile) && <span>Cerrar sesión</span>}
            </button>
          )}
        </div>
      </aside>
    </>
  )
}

export default AdminSidebar