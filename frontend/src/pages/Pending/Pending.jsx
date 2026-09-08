import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Wait from "../../components/Wait";
import { clearToken, API_ENDPOINTS, apiRequest } from "../../config/api";
import "./Pending.css";

export default function Pending() {
  const [user, setUser] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let mounted = true;
    (async () => {
      const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (!mounted) return;
      if (response.ok) {
        setUser(response.data.user ?? response.data);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const handleLogout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  return (
    <div className="pending-page">
      <div className="pending-card">
        <div className="wait-section">
          <Wait />
        </div>

        <div className="message-section">
          <h1 className="pending-title">Estamos procesando tus datos</h1>

          {user && (
            <p className="greeting">Hola, {user.first_name || user.email}</p>
          )}

          <div className="status-badge pending">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 2" />
            </svg>
            <span>Análisis en proceso</span>
          </div>

          <p className="pending-message">
            Te notificaremos por correo cuando tus resultados estén listos.
          </p>
        </div>

        <button className="logout-button" onClick={handleLogout}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9" />
          </svg>
          Cerrar sesión
        </button>
      </div>
    </div>
  );
}
