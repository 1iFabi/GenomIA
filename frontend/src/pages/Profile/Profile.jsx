import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, KeyRound, LogOut, UserX, ShieldCheck } from 'lucide-react';
import { useSession } from '../../hooks/useSession';
import { clearToken } from '../../config/api';
import ChangePasswordModal from '../../components/ChangePasswordModal/ChangePasswordModal';
import DeleteAccountModal from '../../components/DeleteAccountModal/DeleteAccountModal';
import './Profile.css';

/**
 * Página de perfil de cuenta (/profile).
 * Muestra los datos del usuario y permite cambiar contraseña, eliminar la
 * cuenta o cerrar sesión. Accesible desde el DropdownMenu del Navbar.
 */
const Profile = () => {
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);
  const [isDeleteAccountOpen, setIsDeleteAccountOpen] = useState(false);

  if (loading) return null;

  const displayName =
    user?.first_name ||
    user?.firstName ||
    user?.name ||
    user?.username ||
    'Usuario';
  const email = user?.email || '';
  const initial = (email || displayName || 'U')[0]?.toUpperCase() || 'U';

  const logout = async () => {
    await clearToken();
    window.location.href = '/';
  };

  return (
    <div className="profile-page">
      <header className="profile-header">
        <button
          type="button"
          className="profile-back"
          onClick={() => navigate('/dashboard')}
          aria-label="Volver al dashboard"
        >
          <ArrowLeft size={18} aria-hidden="true" />
          <span>Volver al dashboard</span>
        </button>
      </header>

      <main className="profile-main">
        <div className="profile-card">
          <div className="profile-avatar" aria-hidden="true">
            {initial}
          </div>
          <h1 className="profile-name">{displayName}</h1>
          <p className="profile-email">{email}</p>
          <span className="profile-badge">
            <ShieldCheck size={14} aria-hidden="true" />
            Cuenta
          </span>
        </div>

        <section className="profile-actions" aria-label="Acciones de cuenta">
          <button
            type="button"
            className="profile-action"
            onClick={() => setIsChangePasswordOpen(true)}
          >
            <KeyRound size={18} className="profile-action-icon" aria-hidden="true" />
            <span className="profile-action-text">
              <span className="profile-action-title">Cambiar contraseña</span>
              <span className="profile-action-desc">Actualiza tu contraseña de acceso</span>
            </span>
          </button>

          <button
            type="button"
            className="profile-action"
            onClick={logout}
          >
            <LogOut size={18} className="profile-action-icon" aria-hidden="true" />
            <span className="profile-action-text">
              <span className="profile-action-title">Cerrar sesión</span>
              <span className="profile-action-desc">Finaliza tu sesión actual</span>
            </span>
          </button>

          <button
            type="button"
            className="profile-action profile-action--danger"
            onClick={() => setIsDeleteAccountOpen(true)}
          >
            <UserX size={18} className="profile-action-icon" aria-hidden="true" />
            <span className="profile-action-text">
              <span className="profile-action-title">Eliminar cuenta</span>
              <span className="profile-action-desc">Elimina tu cuenta y todos tus datos</span>
            </span>
          </button>
        </section>
      </main>

      <ChangePasswordModal
        isOpen={isChangePasswordOpen}
        onClose={() => setIsChangePasswordOpen(false)}
      />
      <DeleteAccountModal
        isOpen={isDeleteAccountOpen}
        onClose={() => setIsDeleteAccountOpen(false)}
        userName={displayName}
      />
    </div>
  );
};

export default Profile;
