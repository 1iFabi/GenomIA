import { useNavigate } from 'react-router-dom';
import { LayoutDashboard, LogOut, UserRound, ChevronDown } from 'lucide-react';
import { clearToken } from '../../config/api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import './AccountMenu.css';

/**
 * Menú desplegable de cuenta (shadcn DropdownMenu) para el Navbar del landing.
 * Se muestra cuando hay sesión activa, en lugar del botón "Inicia Sesión".
 * Ofrece: Perfil, Ir al dashboard y Cerrar sesión.
 */
const AccountMenu = ({ user, onNavigate, theme = 'light' }) => {
  const navigate = useNavigate();

  const closeMenu = () => onNavigate?.();

  const goTo = (path) => () => {
    closeMenu();
    navigate(path);
  };

  const goProfile = goTo('/profile');
  const goDashboard = goTo('/dashboard');

  const logout = async () => {
    closeMenu();
    await clearToken(); // revoca en el servidor y limpia la cookie HttpOnly
    // Reload para que el Navbar re-inicialice useSession y muestre 'Inicia Sesión' de nuevo.
    window.location.href = '/';
  };

  const initial = (user?.email || 'C')[0]?.toUpperCase() || 'C';
  const isDark = theme === 'dark';
  const contentClass = `z-[200] account-menu-content${isDark ? ' account-menu-content--dark' : ''}`;

  return (
    <div className={`account-menu account-menu--${theme}`}>
      {/* modal={false}: el dropdown no debe bloquear el scroll del body ni
          el pointer de fuera; es un menú no-modal de navbar. */}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="account-trigger"
            aria-label="Menú de cuenta"
          >
            <span className="account-avatar">{initial}</span>
            <ChevronDown size={16} aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className={contentClass}>
          <DropdownMenuLabel className="account-menu-email">
            {user?.email || ''}
          </DropdownMenuLabel>

          <DropdownMenuSeparator className="account-menu-separator" />

          <DropdownMenuItem
            className="account-menu-item account-menu-item--profile"
            onSelect={goProfile}
          >
            <UserRound size={16} className="text-current" aria-hidden="true" />
            <span>Perfil</span>
          </DropdownMenuItem>

          <DropdownMenuItem
            className="account-menu-item account-menu-item--dashboard"
            onSelect={goDashboard}
          >
            <LayoutDashboard size={16} className="text-current" aria-hidden="true" />
            <span>Ir al dashboard</span>
          </DropdownMenuItem>

          <DropdownMenuSeparator className="account-menu-separator" />

          <DropdownMenuItem
            className="account-menu-item account-menu-item--logout"
            variant="destructive"
            onSelect={logout}
          >
            <LogOut size={16} className="text-current" aria-hidden="true" />
            <span>Cerrar sesión</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};

export default AccountMenu;
