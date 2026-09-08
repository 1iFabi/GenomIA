import React, { useEffect, useMemo, useState } from 'react';
import { UserPlus, UserMinus, RefreshCw, Menu, X, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import './AdminAnalystAccess.css';

const AdminAnalystAccess = ({ user }) => {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [modalUser, setModalUser] = useState(null);
  const [selectedRole, setSelectedRole] = useState('analyst');
  const [roleFilter, setRoleFilter] = useState('all');

  const loadUsers = async () => {
    setLoading(true);
    setError('');
    const resp = await apiRequest(API_ENDPOINTS.GET_USERS, { method: 'GET' });
    if (resp.ok) {
      setUsers(resp.data || []);
    } else {
      setError(resp.data?.error || 'No se pudo cargar la lista de usuarios.');
    }
    setLoading(false);
  };

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

  useEffect(() => {
    loadUsers();
  }, []);

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (err) {
      console.error('Error al cerrar sesion', err);
    }
    clearToken();
    navigate('/');
  };

  const analystCount = useMemo(
    () => users.filter((u) => u.is_analyst || u.roles?.includes('ANALISTA')).length,
    [users],
  );

  const receptionCount = useMemo(
    () => users.filter((u) => u.is_reception || u.roles?.includes('RECEPCION')).length,
    [users],
  );

  const getDisplayName = (u) => {
    if (u.first_name && u.last_name) {
      return `${u.first_name} ${u.last_name}`;
    }
    return u.name || u.first_name || u.username || u.email || 'Usuario';
  };

  const getCurrentRole = (targetUser) => {
    if (targetUser.is_analyst || targetUser.roles?.includes('ANALISTA')) return 'analyst';
    if (targetUser.is_reception || targetUser.roles?.includes('RECEPCION')) return 'reception';
    return 'none';
  };

  const updateRole = async (targetUser, roleKey, grant) => {
    const roleLabel = roleKey === 'reception' ? 'Recepción' : 'Analista';
    setSaving(true);
    setError('');
    setMessage('');
    const resp = await apiRequest(API_ENDPOINTS.ADMIN_ANALYSTS, {
      method: 'POST',
      body: JSON.stringify({ userId: targetUser.id, grant, role: roleKey }),
    });

    if (resp.ok) {
      const { is_analyst: isAnalystFlag, is_reception: isReceptionFlag } = resp.data || {};
      setUsers((prev) =>
        prev.map((u) => {
          if (u.id !== targetUser.id) return u;
          const roles = new Set(u.roles || []);
          if (grant) {
            if (roleKey === 'analyst') {
              roles.add('ANALISTA');
              roles.delete('RECEPCION');
            } else {
              roles.add('RECEPCION');
              roles.delete('ANALISTA');
            }
          } else {
            if (roleKey === 'analyst') {
              roles.delete('ANALISTA');
            } else {
              roles.delete('RECEPCION');
            }
          }

          const nextAnalyst =
            typeof isAnalystFlag === 'boolean' ? isAnalystFlag : roleKey === 'analyst' ? grant : false;
          const nextReception =
            typeof isReceptionFlag === 'boolean'
              ? isReceptionFlag
              : roleKey === 'reception'
              ? grant
              : false;

          return {
            ...u,
            is_analyst: nextAnalyst,
            is_reception: nextReception,
            roles: Array.from(roles),
          };
        }),
      );
      setMessage(
        grant
          ? `Permiso de ${roleLabel} asignado correctamente.`
          : 'Acceso retirado correctamente.',
      );
    } else {
      setError(resp.data?.error || 'No se pudo actualizar el permiso.');
    }
    setSaving(false);
  };

  const openModal = (targetUser) => {
    const current = getCurrentRole(targetUser);
    setSelectedRole(current === 'none' ? 'analyst' : current);
    setModalUser(targetUser);
  };

  const closeModal = () => setModalUser(null);

  const submitRoleChange = async () => {
    if (!modalUser) return;
    const currentRole = getCurrentRole(modalUser);
    if (selectedRole === 'none') {
      if (currentRole === 'none') {
        setError('El usuario ya no tiene accesos especiales.');
        setModalUser(null);
        return;
      }
      await updateRole(modalUser, currentRole, false);
    } else {
      await updateRole(modalUser, selectedRole, true);
    }
    setModalUser(null);
  };

  const visibleUsers = useMemo(() => {
    let filtered = users.filter((u) => u.id !== user?.id);

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter((u) => {
        const fullName = getDisplayName(u).toLowerCase();
        const email = (u.email || '').toLowerCase();
        const username = (u.username || '').toLowerCase();
        return fullName.includes(term) || email.includes(term) || username.includes(term);
      });
    }

    if (roleFilter !== 'all') {
      filtered = filtered.filter((u) => {
        const currentRole = getCurrentRole(u);
        return roleFilter === 'none' ? currentRole === 'none' : currentRole === roleFilter;
      });
    }

    return filtered;
  }, [users, user?.id, searchTerm, roleFilter]);

  const isAdmin = user?.is_staff || user?.is_superuser || user?.roles?.includes('ADMIN');

  return (
    <div className="admin-analysts-wrapper">
      {isMobile && (
        <button
          className="admin-analysts__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      )}

      <aside className="admin-analysts__sidebar">
        <AdminSidebar
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
          isAdmin={isAdmin}
        />
      </aside>

      <main className="admin-analysts">
        <div className="admin-analysts__header">
          <div className="admin-analysts__headline">
            <h1 className="admin-analysts__title">Otorgar Permisos</h1>
            <p className="admin-analysts__subtitle">
              Asigna o revoca acceso a las vistas especiales de Analista o Recepción. Solo pueden tener
              un rol privilegiado a la vez.
            </p>
          </div>
          <div className="admin-analysts__meta">
            <button type="button" className="admin-analysts__refresh" onClick={loadUsers} disabled={loading}>
              <RefreshCw size={16} />
              Recargar
            </button>
          </div>
        </div>

        <div className="admin-analysts__search-card">
          <div className="admin-analysts__search-row">
            <div className="admin-analysts__search-input-container">
              <Search size={18} className="admin-analysts__search-icon" />
              <input
                type="text"
                placeholder="Buscar por nombre, email o usuario..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="admin-analysts__search-input"
              />
            </div>
            <div className="admin-analysts__filters">
              <label htmlFor="role-filter">Filtrar por rol:</label>
              <select
                id="role-filter"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="admin-analysts__select"
              >
                <option value="all">Todos</option>
                <option value="analyst">Analista</option>
                <option value="reception">Recepción</option>
                <option value="none">Sin rol</option>
              </select>
            </div>
          </div>
        </div>

        {error && (
          <div className="analyst-access__alert analyst-access__alert--error">
            <span>{error}</span>
            <button type="button" className="analyst-access__alert-close" onClick={() => setError('')} aria-label="Cerrar alerta de error">
              <X size={16} />
            </button>
          </div>
        )}
        {message && (
          <div className="analyst-access__alert analyst-access__alert--success">
            <span>{message}</span>
            <button type="button" className="analyst-access__alert-close" onClick={() => setMessage('')} aria-label="Cerrar alerta de éxito">
              <X size={16} />
            </button>
          </div>
        )}

        <div className="analyst-access__card">
          <div className="analyst-access__card-header">
            <div>
              <h2>Usuarios</h2>
              <span className="analyst-access__subtitle">
                Elige Analista o Recepción (solo una opción) y confirma antes de aplicar.
              </span>
            </div>
            <div className="analyst-access__legend">
              <span className="analyst-access__chip analyst-access__chip--admin">ADMIN</span>
              <span className="analyst-access__chip analyst-access__chip--analyst">ANALISTA</span>
              <span className="analyst-access__chip analyst-access__chip--reception">RECEPCIÓN</span>
            </div>
          </div>

          {loading ? (
            <div className="analyst-access__loading">Cargando usuarios...</div>
          ) : (
            <div className="analyst-access__table" role="table" aria-label="Usuarios y permisos">
              <div className="analyst-access__row analyst-access__row--head" role="row">
                <span>Usuario</span>
                <span>Email</span>
                <span>Rol asignado</span>
                <span className="analyst-access__align-center">Acción</span>
              </div>
              {visibleUsers.length === 0 ? (
                <div className="analyst-access__loading">No se encontraron usuarios.</div>
              ) : (
                visibleUsers.map((u) => {
                  const isAnalyst = u.is_analyst || u.roles?.includes('ANALISTA');
                  const isReception = u.is_reception || u.roles?.includes('RECEPCION');
                  const isAdminUser = u.is_admin || u.roles?.includes('ADMIN') || u.is_staff;
                  const currentRole = getCurrentRole(u);
                  return (
                    <div key={u.id} className="analyst-access__row" role="row">
                      <span>{getDisplayName(u)}</span>
                      <span className="analyst-access__muted">{u.email}</span>
                      <span className="analyst-access__tags">
                        {isAdminUser && <span className="analyst-access__chip analyst-access__chip--admin">ADMIN</span>}
                        {isAnalyst && (
                          <span className="analyst-access__chip analyst-access__chip--analyst">ANALISTA</span>
                        )}
                        {isReception && (
                          <span className="analyst-access__chip analyst-access__chip--reception">RECEPCIÓN</span>
                        )}
                        {!isAdminUser && !isAnalyst && !isReception && (
                          <span className="analyst-access__chip analyst-access__chip--user">USUARIO</span>
                        )}
                      </span>
                      <span className="analyst-access__align-center">
                        <button
                          type="button"
                          className="analyst-access__toggle analyst-access__toggle--primary"
                          onClick={() => openModal(u)}
                          disabled={saving}
                        >
                          {currentRole === 'none' ? <UserPlus size={16} /> : <UserMinus size={16} />}
                          {currentRole === 'none' ? 'Otorgar poder' : 'Cambiar / Quitar'}
                        </button>
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </main>

      {modalUser && (
        <div className="analyst-modal__backdrop" role="dialog" aria-modal="true">
          <div className="analyst-modal">
            <div className="analyst-modal__header">
              <div>
                <p className="analyst-modal__eyebrow">Confirmar permiso</p>
                <h3 className="analyst-modal__title">Otorgar poder</h3>
              </div>
              <button
                type="button"
                className="analyst-modal__close"
                aria-label="Cerrar modal"
                onClick={closeModal}
              >
                <X size={18} />
              </button>
            </div>
            <p className="analyst-modal__hint">
              Solo puede tener Analista o Recepción (una a la vez). El cambio sobrescribe el rol anterior.
            </p>
            <div className="analyst-modal__user">
              <div className="analyst-modal__user-name">{getDisplayName(modalUser)}</div>
              <div className="analyst-modal__user-email">{modalUser.email}</div>
            </div>
            <div className="analyst-modal__options">
              <label className="analyst-modal__option">
                <input
                  type="radio"
                  value="analyst"
                  checked={selectedRole === 'analyst'}
                  onChange={(e) => setSelectedRole(e.target.value)}
                />
                <div>
                  <div className="analyst-modal__option-title">Analista</div>
                  <div className="analyst-modal__option-desc">Acceso a vista avanzada y gestión.</div>
                </div>
              </label>
              <label className="analyst-modal__option">
                <input
                  type="radio"
                  value="reception"
                  checked={selectedRole === 'reception'}
                  onChange={(e) => setSelectedRole(e.target.value)}
                />
                <div>
                  <div className="analyst-modal__option-title">Recepción</div>
                  <div className="analyst-modal__option-desc">Permite operar la vista de recepción.</div>
                </div>
              </label>
              <label className="analyst-modal__option">
                <input
                  type="radio"
                  value="none"
                  checked={selectedRole === 'none'}
                  onChange={(e) => setSelectedRole(e.target.value)}
                />
                <div>
                  <div className="analyst-modal__option-title">Quitar acceso</div>
                  <div className="analyst-modal__option-desc">Remueve cualquier rol especial asignado.</div>
                </div>
              </label>
            </div>
            <div className="analyst-modal__actions">
              <button type="button" className="analyst-modal__button analyst-modal__button--ghost" onClick={closeModal}>
                Cancelar
              </button>
              <button
                type="button"
                className="analyst-modal__button analyst-modal__button--primary"
                onClick={submitRoleChange}
                disabled={saving}
              >
                {saving ? 'Guardando...' : 'Confirmar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminAnalystAccess;
