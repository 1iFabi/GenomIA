import { useEffect, useState } from 'react';
import { useAuthSession } from '../contexts/AuthContext';

/**
 * La cookie HttpOnly se verifica con /me una vez por sesión compartida.
 * Un guard puede pasar su ruta para reintentar una comprobación fallida al navegar.
 */
export const useSession = (checkKey) => {
  const session = useAuthSession();
  const [checked, setChecked] = useState(null);

  useEffect(() => {
    session.ensureSession();
    setChecked({ key: checkKey });
  }, [session.ensureSession, checkKey]);

  // A new consumer must start its check before acting on an earlier failure.
  // Authenticated consumers reuse the cached user immediately.
  const loading = session.loading || (!session.user && (!checked || checked.key !== checkKey));
  return { user: session.user, isLoggedIn: !!session.user, loading };
};
