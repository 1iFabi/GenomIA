import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { API_ENDPOINTS, apiRequest, subscribeAuthChanges } from '../config/api';

const AuthContext = createContext(null);
const initialSession = () => ({ user: null, loading: true });

export function AuthProvider({ children }) {
  const [session, setSession] = useState(initialSession);
  const sessionRef = useRef(session);
  const pendingRequest = useRef(null);
  const generation = useRef(0);
  const signedOut = useRef(false);

  const publish = useCallback((next) => {
    sessionRef.current = next;
    setSession(next);
  }, []);

  useEffect(() => subscribeAuthChanges(({ type }) => {
    generation.current += 1;
    pendingRequest.current = null;
    signedOut.current = type === 'logout';
    publish(type === 'login' ? initialSession() : {
      user: null,
      loading: false,
    });
  }), [publish]);

  const ensureSession = useCallback(() => {
    if (sessionRef.current.user || signedOut.current || pendingRequest.current) return;
    const requestGeneration = generation.current;
    publish(initialSession());
    // Keep this promise through effect cleanup/replay; it belongs to the provider,
    // not a route. Only logout/login/expiry invalidates an in-flight result.
    pendingRequest.current = (async () => {
      let response;
      try {
        response = await Promise.resolve().then(() => apiRequest(API_ENDPOINTS.ME, { method: 'GET' }));
      } catch {
        response = { ok: false };
      }
      if (requestGeneration !== generation.current) return;
      pendingRequest.current = null;
      publish({
        user: response.ok ? (response.data?.user ?? response.data ?? null) : null,
        loading: false,
      });
    })();
  }, [publish]);

  return (
    <AuthContext.Provider value={{ ...session, ensureSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthSession() {
  const session = useContext(AuthContext);
  if (!session) throw new Error('useSession requires an AuthProvider');
  return session;
}
