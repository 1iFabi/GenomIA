import React, { useMemo, useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { LogOut, Dna, Activity, Heart, Globe, Pill, TestTube, User, ChevronDown, ChevronUp, KeyRound, UserX, MessageCircle, Grid3x3 } from 'lucide-react'
import { Home } from 'lucide-react'
import ChangePasswordModal from '../ChangePasswordModal/ChangePasswordModal.jsx'
import DeleteAccountModal from '../DeleteAccountModal/DeleteAccountModal.jsx'
import './Sidebar.css'

const defaultCategoryIcons = [Dna, Activity, Heart, Globe, Pill, TestTube]
const defaultIcons = {
  profile: User,
  profileExpand: ChevronDown,
  profileCollapse: ChevronUp,
  key: KeyRound,
  removeAccount: UserX,
  categories: Grid3x3,
  categoriesExpand: ChevronDown,
  categoriesCollapse: ChevronUp,
  categoryItems: defaultCategoryIcons,
  aiExpand: ChevronDown,
  aiCollapse: ChevronUp,
  chat: MessageCircle,
  home: Home,
  logout: LogOut,
}
const noop = () => {}

const Sidebar = ({ items = [], onLogout, user, isMobileMenuOpen = false, setIsMobileMenuOpen = noop, iconOverrides }) => {
  const navigate = useNavigate()
  const location = useLocation()
  const [isHovered, setIsHovered] = useState(false)
  const [isProfileExpanded, setIsProfileExpanded] = useState(false)
  const [isCategoriesExpanded, setIsCategoriesExpanded] = useState(false)
  const [isAIExpanded, setIsAIExpanded] = useState(false)
  const [isChangePasswordModalOpen, setIsChangePasswordModalOpen] = useState(false)
  const [isDeleteAccountModalOpen, setIsDeleteAccountModalOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const Icons = { ...defaultIcons, ...iconOverrides }
  const base = import.meta.env.BASE_URL || '/'
  const nalaImg = `${base}nala.png`

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

  useEffect(() => {
    if (!isMobile) return
    const html = document.documentElement
    const prev = html.style.overflow
    html.style.overflow = isMobileMenuOpen ? 'hidden' : prev || ''
    return () => {
      html.style.overflow = prev || ''
    }
  }, [isMobileMenuOpen, isMobile])

  useEffect(() => {
    // Close mobile overlay on route change to avoid a stuck dark screen
    if (isMobileMenuOpen) {
      setIsMobileMenuOpen(false)
    }
  }, [location.pathname, isMobileMenuOpen, setIsMobileMenuOpen])

  const navItems = useMemo(() => {
    return items.map((it, idx) => {
      const Icon = iconOverrides?.categoryItems?.[idx]
        || defaultCategoryIcons[idx % defaultCategoryIcons.length]
      return {
        label: it.label ?? String(it),
        href: it.href ?? '#',
        Icon,
      }
    })
  }, [iconOverrides, items])

  const displayName = useMemo(() => {
    return user?.first_name || user?.firstName || user?.name || 'Usuario'
  }, [user])

  const toggleProfile = (e) => {
    e.preventDefault()
    setIsProfileExpanded(!isProfileExpanded)
  }

  const toggleCategories = (e) => {
    e.preventDefault()
    setIsCategoriesExpanded(!isCategoriesExpanded)
  }

  const toggleAI = (e) => {
    e.preventDefault()
    setIsAIExpanded(!isAIExpanded)
  }

  const closeMenuAndNavigate = (href) => (e) => {
    e.preventDefault();
    if (isMobile) {
      setIsMobileMenuOpen(false)
    }
    navigate(href)
  }

  const isExpanded = isHovered;

  return (
    <>
      <div 
        className={`sidebar__overlay ${isMobile && isMobileMenuOpen ? 'sidebar__overlay--open' : ''}`}
        onClick={() => setIsMobileMenuOpen(false)}
        aria-hidden={!isMobileMenuOpen}
      />

      <aside 
        className={`sidebar ${
          isExpanded ? 'sidebar--unfolded' : 'sidebar--folded'
        } ${
          isMobile && isMobileMenuOpen ? 'sidebar--mobile-open' : ''
        }`}
        onMouseEnter={() => !isMobile && setIsHovered(true)}
        onMouseLeave={() => !isMobile && setIsHovered(false)}
      >
      <div className="sidebar__header">
        <button
          type="button"
          className="sidebar__brand"
          onClick={() => {
            if (isMobile) setIsMobileMenuOpen(false)
            navigate('/dashboard')
          }}
          aria-label="Ir al dashboard"
        >
          <img src="/cSolido.png" alt="GenomIA Logo" className="sidebar__logo" />
          {isExpanded && !isMobile && <span className="sidebar__brand-text">Genom<span className="sidebar__brand-highlight">IA</span>.</span>}
        </button>
      </div>

      <nav className="sidebar__nav">
        <div className="sidebar__profile-section">
          <button 
            type="button" 
            className="sidebar__nav-item sidebar__profile-toggle"
            onClick={toggleProfile}
            title={!isExpanded && !isMobile ? 'Perfil' : undefined}
          >
            <Icons.profile size={20} className="sidebar__nav-icon" aria-hidden="true" />
            {(isExpanded || isMobile) && (
              <>
                <span className="sidebar__nav-label">Perfil</span>
                {isProfileExpanded
                  ? <Icons.profileCollapse size={16} aria-hidden="true" />
                  : <Icons.profileExpand size={16} aria-hidden="true" />}
              </>
            )}
          </button>

          {isProfileExpanded && (isExpanded || isMobile) && (
            <div className="sidebar__profile-content">
              <div className="sidebar__profile-greeting">
                Hola {displayName}
              </div>
              <ul className="sidebar__profile-menu">
                <li>
                  <button 
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      setIsChangePasswordModalOpen(true);
                      if (isMobile) setIsMobileMenuOpen(false);
                    }}
                    className="sidebar__profile-item sidebar__profile-button"
                  >
                    <Icons.key size={18} className="sidebar__profile-icon" aria-hidden="true" />
                    <span>Cambiar contraseña</span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault()
                      setIsDeleteAccountModalOpen(true)
                      if (isMobile) setIsMobileMenuOpen(false);
                    }}
                    className="sidebar__profile-item sidebar__profile-item--danger sidebar__profile-button"
                  >
                    <Icons.removeAccount size={18} className="sidebar__profile-icon" aria-hidden="true" />
                    <span>Eliminar cuenta</span>
                  </button>
                </li>
              </ul>
            </div>
          )}
        </div>

        {(isExpanded || isMobile) && <div className="sidebar__divider" />}

        <div className="sidebar__categories-section">
          <button 
            type="button" 
            className="sidebar__nav-item sidebar__categories-toggle"
            onClick={toggleCategories}
            title={!isExpanded && !isMobile ? 'Categorías' : undefined}
          >
            <Icons.categories size={20} className="sidebar__nav-icon" aria-hidden="true" />
            {(isExpanded || isMobile) && (
              <>
                <span className="sidebar__nav-label">Categorías</span>
                {isCategoriesExpanded
                  ? <Icons.categoriesCollapse size={16} aria-hidden="true" />
                  : <Icons.categoriesExpand size={16} aria-hidden="true" />}
              </>
            )}
          </button>

          {isCategoriesExpanded && (isExpanded || isMobile) && (
            <div className="sidebar__categories-content">
              <ul className="sidebar__categories-menu">
                {navItems.map((nav) => (
                  <li key={nav.label}>
                    <button
                      type="button"
                      className="sidebar__categories-item"
                      onClick={closeMenuAndNavigate(nav.href)}
                    >
                      <nav.Icon size={18} className="sidebar__categories-icon" aria-hidden="true" />
                      <span>{nav.label}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {(isExpanded || isMobile) && <div className="sidebar__divider" />}

        <div className="sidebar__ai-section">
          <button 
            type="button" 
            className="sidebar__nav-item sidebar__ai-toggle"
            onClick={toggleAI}
            title={!isExpanded && !isMobile ? 'Pregúntale a Nala' : undefined}
          >
            <span
              className="sidebar__nav-icon sidebar__nav-avatar"
              style={{ backgroundImage: `url(${nalaImg})` }}
              aria-hidden
            />
            {(isExpanded || isMobile) && (
              <>
                <span className="sidebar__nav-label">Pregúntale a Nala</span>
                {isAIExpanded
                  ? <Icons.aiCollapse size={16} aria-hidden="true" />
                  : <Icons.aiExpand size={16} aria-hidden="true" />}
              </>
            )}
          </button>

          {isAIExpanded && (isExpanded || isMobile) && (
            <div className="sidebar__ai-content">
              <ul className="sidebar__ai-menu">
                <li>
                  <a 
                    href="#chatear-ia" 
                    className="sidebar__ai-item"
                    onClick={closeMenuAndNavigate('#chatear-ia')}
                  >
                    <Icons.chat size={18} className="sidebar__ai-icon" aria-hidden="true" />
                    <span>Chatea con la IA</span>
                  </a>
                </li>
              </ul>
            </div>
          )}
        </div>

      </nav>

      <div className="sidebar__footer">
        <button
          type="button"
          className="sidebar__home"
          onClick={() => { if (isMobile) setIsMobileMenuOpen(false); navigate('/'); }}
          title={!isExpanded && !isMobile ? 'Volver al inicio' : undefined}
        >
          <Icons.home size={20} aria-hidden="true" />
          {(isExpanded || isMobile) && <span>Volver al inicio</span>}
        </button>
        {onLogout && (
          <button 
            type="button" 
            className="sidebar__logout" 
            onClick={() => {
              if (isMobile) setIsMobileMenuOpen(false)
              onLogout()
            }}
            title={!isExpanded && !isMobile ? 'Cerrar sesión' : undefined}
          >
            <Icons.logout size={20} aria-hidden="true" />
            {(isExpanded || isMobile) && <span>Cerrar sesión</span>}
          </button>
        )}
      </div>

      </aside>

      {createPortal(
        <>
          <ChangePasswordModal 
            isOpen={isChangePasswordModalOpen}
            onClose={() => setIsChangePasswordModalOpen(false)}
          />
          <DeleteAccountModal
            isOpen={isDeleteAccountModalOpen}
            onClose={() => {
              setIsDeleteAccountModalOpen(false)
              setIsProfileExpanded(false)
            }}
            userName={displayName}
          />
        </>,
        document.body
      )}
    </>
  )
}

export default Sidebar
