import { useEffect, useState } from 'react';
import { API_ENDPOINTS, apiRequest } from '../config/api';

/**
 * Determina si hay una sesión activa consultando /me.
 * El token vive en cookie HttpOnly (ilegible por JS), así que la única forma
 * de saber si el usuario está logueado es preguntarle al backend.
 */
export const useSession = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const res = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (!mounted) return;
      if (res.ok && res.data.user) {
        setUser(res.data.user);
      }
      setLoading(false);
    })();
    return () => { mounted = false; };
  }, []);

  return { user, isLoggedIn: !!user, loading };
};
