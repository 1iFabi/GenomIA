import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiRequest, API_ENDPOINTS, clearToken } from '../../config/api';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import SearchSample from '../../components/SearchSample/SearchSample';
import './PostloginReception.css';
import { AlertCircle, CheckCircle2, Printer, CheckSquare, X } from 'lucide-react';

import SkeletonCard from '../../components/SkeletonCard/SkeletonCard';

const PostloginReception = ({ user }) => {
  const navigate = useNavigate();
  const [selectedUser, setSelectedUser] = useState(null);
  const [checklist, setChecklist] = useState({
    rut: false,
    nombre: false,
    consentimiento: false,
    entiende: false,
    muestra: false,
    etiqueta: false,
  });

  const handleChecklistChange = (item) => {
    setChecklist((prev) => ({ ...prev, [item]: !prev[item] }));
  };
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (err) {
      console.error('Error al cerrar sesión', err);
    }
    clearToken();
    navigate('/');
  };

  const resetMessages = () => {
    setError('');
    setInfo('');
    setChecklist({
      rut: false,
      nombre: false,
      consentimiento: false,
      entiende: false,
      muestra: false,
      etiqueta: false,
    });
  };

  const handleSearch = async (sampleId) => {
    resetMessages();
    if (!sampleId) {
      setError('Ingresa un SampleID para buscar.');
      return;
    }
    setLoadingSearch(true);
    const params = new URLSearchParams();
    params.append('sample_code', sampleId.trim());

    const response = await apiRequest(`${API_ENDPOINTS.RECEPTION_SEARCH}?${params.toString()}`, { method: 'GET' });
    setLoadingSearch(false);
    if (!response.ok) {
      setError(response.data?.error || 'No se pudo buscar. Intenta de nuevo.');
      return;
    }
    const found = response.data?.results || [];
    if (found.length === 1) {
      setSelectedUser(found[0]);
    } else {
      setSelectedUser(null);
      setInfo('No se encontraron usuarios con ese SampleID.');
    }
  };

  const handlePrint = (userPayload = selectedUser) => {
    if (!userPayload?.sample_code) return;
    const win = window.open('', 'PRINT', 'height=480,width=320');
    const name = `${userPayload.first_name || ''} ${userPayload.last_name || ''}`.trim();
    win.document.write(`
      <html>
        <head>
          <title>Etiqueta SampleCode</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 16px; }
            .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; text-align: center; }
            .code { font-size: 22px; font-weight: 800; letter-spacing: 1px; margin: 8px 0; }
            .meta { font-size: 13px; color: #4b5563; }
          </style>
        </head>
        <body onload="window.print(); window.close();">
          <div class="card">
            <div>SampleCode</div>
            <div class="code">${userPayload.sample_code}</div>
            <div class="meta">${name || 'Usuario'}</div>
            <div class="meta">${userPayload.rut || ''}</div>
          </div>
        </body>
      </html>
    `);
    win.document.close();
  };

  const checklistComplete = Object.values(checklist).every(Boolean);

  const handleCompletePending = async () => {
    if (!selectedUser?.user_id) {
      setError('Selecciona un Sample ID primero.');
      return;
    }
    if (!checklistComplete) {
      setError('Marca todas las verificaciones antes de continuar.');
      return;
    }
    resetMessages();
    // Llamar a sample-code para asegurar SampleCode y dejar service_status en PENDING
    const body = { userId: selectedUser.user_id, resend: false };
    const resp = await apiRequest(API_ENDPOINTS.RECEPTION_SAMPLE_CODE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      setError(resp.data?.error || 'No se pudo actualizar a pendiente.');
      return;
    }
    const updated = resp.data?.user || selectedUser;
    setSelectedUser(updated);
    setInfo('Estado actualizado a pendiente.');
  };
  
  const displayName = useMemo(() => {
    const candidates = [
      user?.first_name,
      user?.firstName,
      user?.name,
      user?.username,
      user?.email,
    ];
    return candidates.find(Boolean) || 'Recepción';
  }, [user]);

  return (
    <div className="postlogin-reception">
      <aside className="postlogin-reception__sidebar">
        <AdminSidebar onLogout={handleLogout} user={user} showNavItems={false} />
      </aside>
      <main className="postlogin-reception__main">
        <header className="postlogin-reception__header">
          <div className="postlogin-reception__headline">
            <h1 className="postlogin-reception__title">Bienvenido/a {displayName}</h1>
            <p className="postlogin-reception__subtitle">
              Busca una muestra por su SampleID para verificar la identidad del usuario y etiquetar la muestra.
            </p>
          </div>
        </header>

        <div className="reception-content">
          <div className="reception-search-container">
            <SearchSample onSearch={handleSearch} loading={loadingSearch} />
            {error && (
              <div className="reception-alert reception-alert--error">
                <AlertCircle size={16} />
                <span>{error}</span>
                <button onClick={resetMessages} className="reception-alert__close">
                  <X size={16} />
                </button>
              </div>
            )}
            {info && (
              <div className="reception-alert reception-alert--info">
                <CheckCircle2 size={16} />
                <span>{info}</span>
                <button onClick={resetMessages} className="reception-alert__close">
                  <X size={16} />
                </button>
              </div>
            )}
          </div>

          {loadingSearch ? (
            <div className="reception-details">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : selectedUser ? (
            selectedUser.service_status === 'PENDING' ? (
              <div className="reception-pending-message">
                <CheckCircle2 size={32} className="reception-pending-message__icon" />
                <h2 className="reception-pending-message__title">Muestra en estado Pendiente</h2>
                <p className="reception-pending-message__text">
                  El Sample ID <strong>{selectedUser.sample_code}</strong> ya ha sido procesado y está pendiente de resultados.
                </p>
                <button className="reception-btn reception-btn--primary" onClick={() => setSelectedUser(null)}>
                  Buscar otra muestra
                </button>
              </div>
            ) : (
              <div className="reception-details">
                <div className="reception-user-card">
                  <div className="reception-user-card__header">
                    <div>
                      <p className="reception-user-card__label">Sample ID</p>
                      <h2 className="reception-user-card__code">{selectedUser.sample_code || '—'}</h2>
                    </div>
                    <span className={`reception-badge ${selectedUser.sample_status?.includes('PENDING') ? 'reception-badge--pending' : 'reception-badge--default'}`}>
                      {selectedUser.sample_status_display || selectedUser.service_status || 'Pendiente'}
                    </span>
                  </div>
                  <div className="reception-user-card__body">
                    <div className="reception-user-card__row">
                      <div>
                        <p className="reception-user-card__label">Paciente</p>
                        <p className="reception-user-card__value">
                          {(selectedUser.first_name || '')} {(selectedUser.last_name || '')}
                        </p>
                      </div>
                      <div>
                        <p className="reception-user-card__label">RUT</p>
                        <p className="reception-user-card__value">{selectedUser.rut || '—'}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="reception-checklist-card">
                  <h3 className="reception-checklist-card__title">Checklist de recepción</h3>
                  <div className="reception-checklist">
                    <div className="reception-checklist-group">
                      <h4 className="reception-checklist-group__title">Verificación de Identidad (Cédula vs. Sistema)</h4>
                      <label className={`reception-checkbox ${checklist.rut ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.rut} onChange={() => handleChecklistChange('rut')} />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">RUT Coincide</span>
                      </label>
                      <label className={`reception-checkbox ${checklist.nombre ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.nombre} onChange={() => handleChecklistChange('nombre')} />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">Nombre y Apellido Coinciden</span>
                      </label>
                    </div>
                    <div className="reception-checklist-group">
                      <h4 className="reception-checklist-group__title">Verificación de Consentimiento</h4>
                      <label className={`reception-checkbox ${checklist.consentimiento ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.consentimiento} onChange={() => handleChecklistChange('consentimiento')} />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">Consentimiento Informado Firmado</span>
                      </label>
                      <label className={`reception-checkbox ${checklist.entiende ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.entiende} onChange={() => handleChecklistChange('entiende')} />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">Paciente entiende el procedimiento</span>
                      </label>
                    </div>
                    <div className="reception-checklist-group">
                      <h4 className="reception-checklist-group__title">Etiquetado de Muestra</h4>
                      <label className={`reception-checkbox ${checklist.muestra ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.muestra} onChange={() => handleChecklistChange('muestra')} />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">Muestra biológica recepcionada</span>
                      </label>
                      <label className={`reception-checkbox ${checklist.etiqueta ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.etiqueta} onChange={() => handleChecklistChange('etiqueta')} />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">Etiqueta con SampleID impresa y adherida</span>
                      </label>
                    </div>
                  </div>
                  <div className="reception-checklist-card__actions">
                    <button
                      className="reception-btn reception-btn--ghost"
                      onClick={() => handlePrint()}
                      disabled={!selectedUser?.sample_code}
                    >
                      <Printer size={16} /> Imprimir etiqueta
                    </button>
                    <button
                      className="reception-btn reception-btn--primary"
                      onClick={handleCompletePending}
                      disabled={!checklistComplete}
                    >
                      Completar y marcar pendiente
                    </button>
                  </div>
                </div>
              </div>
            )
          ) : null}
        </div>
      </main>
    </div>
  );
};

export default PostloginReception;
