import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiRequest, API_ENDPOINTS, clearToken } from '../../config/api';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import SearchSample from '../../components/SearchSample/SearchSample';
import './PostloginReception.css';
import { AlertCircle, CheckCircle2, Printer, CheckSquare, X } from 'lucide-react';

import SkeletonCard from '../../components/SkeletonCard/SkeletonCard';

const STATUS_LABELS = {
  NO_PURCHASED: 'Sin servicio',
  WAITING_SAMPLE: 'Esperando muestra',
  SAMPLE_RECEIVED: 'Muestra recibida',
  PROCESSING: 'En análisis',
  COMPLETED: 'Completado',
};
const EMPTY_CHECKLIST = {
  rut: false,
  nombre: false,
  consentimiento: false,
  entiende: false,
  muestra: false,
  etiqueta: false,
};

const PostloginReception = ({ user }) => {
  const navigate = useNavigate();
  const [selectedUser, setSelectedUser] = useState(null);
  const [checklist, setChecklist] = useState(EMPTY_CHECKLIST);
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [rutInput, setRutInput] = useState('');
  const [rutMatches, setRutMatches] = useState(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const handleChecklistChange = (item) => {
    setChecklist((prev) => ({ ...prev, [item]: !prev[item] }));
  };

  const handleLogout = async () => {
    try {
      await clearToken();
    } catch (err) {
      console.error('Error al cerrar sesión', err);
    }
    navigate('/');
  };

  const resetMessages = () => {
    setError('');
    setInfo('');
    setChecklist(EMPTY_CHECKLIST);
    setRutInput('');
    setRutMatches(null);
  };

  const search = async (query) => {
    const params = new URLSearchParams({ sample_code: query.trim() });
    const response = await apiRequest(`${API_ENDPOINTS.RECEPTION_SEARCH}?${params.toString()}`, { method: 'GET' });
    if (!response.ok) {
      setError(response.data?.error || 'No se pudo buscar. Intenta de nuevo.');
      return null;
    }
    return response.data?.results || [];
  };

  const handleSearch = async (query) => {
    resetMessages();
    if (!query?.trim()) {
      setError('Ingresa un Sample ID para buscar.');
      return;
    }
    setLoadingSearch(true);
    const found = await search(query);
    setLoadingSearch(false);
    if (found === null) return;
    if (found.length === 1) {
      setSelectedUser(found[0]);
    } else {
      setSelectedUser(null);
      setInfo('No se encontró ningún cliente con ese Sample ID.');
    }
  };

  const handleConfirmPayment = async () => {
    resetMessages();
    setConfirming(true);
    const response = await apiRequest(API_ENDPOINTS.CONFIRM_PAYMENT, {
      method: 'POST',
      body: JSON.stringify({ userId: selectedUser.user_id }),
    });
    if (!response.ok) {
      setConfirming(false);
      setError(response.data?.error || 'No se pudo confirmar el pago.');
      return;
    }
    const { sampleCode, sampleEmailSent } = response.data;
    const refreshed = await search(sampleCode);
    setConfirming(false);
    if (refreshed?.length === 1) setSelectedUser(refreshed[0]);
    setInfo(sampleEmailSent
      ? `Pago confirmado. Sample ID ${sampleCode} enviado al correo del cliente.`
      : `Pago confirmado. Sample ID ${sampleCode}. No se pudo enviar el correo: entrégaselo al cliente.`);
  };

  // The RUT is never sent to the browser (Ley 21.719): reception types it and the backend answers match/no match.
  const handleVerifyRut = async () => {
    setError('');
    const response = await apiRequest(API_ENDPOINTS.RECEPTION_VERIFY_RUT, {
      method: 'POST',
      body: JSON.stringify({ userId: selectedUser.user_id, rut: rutInput.trim() }),
    });
    if (!response.ok) {
      setError(response.data?.error || response.data?.detail || 'No se pudo verificar el RUT.');
      return;
    }
    setRutMatches(response.data.matches);
    setChecklist((prev) => ({ ...prev, rut: response.data.matches }));
  };

  const sampleCode = selectedUser?.service_samples?.[0]?.sample_code || selectedUser?.client_code || '';
  const statusCode = selectedUser?.service_request_status || selectedUser?.service_status;
  const hasService = Boolean(selectedUser?.service_request_status);

  const handlePrint = () => {
    if (!sampleCode) return;
    const win = window.open('', 'PRINT', 'height=480,width=320');
    if (!win) return;

    const printDocument = win.document;
    const name = [selectedUser.first_name || '', selectedUser.last_name || '']
      .filter(Boolean)
      .join(' ')
      .trim();
    const style = printDocument.createElement('style');
    style.textContent = `
      body { font-family: Arial, sans-serif; padding: 16px; }
      .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; text-align: center; }
      .code { font-size: 22px; font-weight: 800; letter-spacing: 1px; margin: 8px 0; }
      .meta { font-size: 13px; color: #4b5563; }
    `;
    printDocument.head.appendChild(style);
    printDocument.title = 'Etiqueta SampleCode';

    const createTextElement = (tagName, className, text) => {
      const element = printDocument.createElement(tagName);
      if (className) element.className = className;
      element.textContent = text;
      return element;
    };

    const card = printDocument.createElement('div');
    card.className = 'card';
    card.append(
      createTextElement('div', '', 'SampleCode'),
      createTextElement('div', 'code', sampleCode),
      createTextElement('div', 'meta', name || 'Usuario'),
    );
    printDocument.body.appendChild(card);

    const printAndClose = () => {
      win.print();
      win.close();
    };
    if (printDocument.readyState === 'complete') {
      setTimeout(printAndClose, 0);
    } else {
      win.addEventListener('load', printAndClose, { once: true });
    }
    printDocument.close();
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
              Busca al cliente por su Sample ID para confirmar su pago o recibir su muestra.
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
            <div className="reception-details">
              <div className="reception-user-card">
                <div className="reception-user-card__header">
                  <div>
                    <p className="reception-user-card__label">Sample ID</p>
                    <h2 className="reception-user-card__code">{sampleCode || '—'}</h2>
                  </div>
                  <span className={`reception-badge ${hasService ? 'reception-badge--pending' : 'reception-badge--default'}`}>
                    {STATUS_LABELS[statusCode] || statusCode}
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
                  </div>
                </div>
                {!hasService && (
                  <div className="reception-checklist-card__actions">
                    <button
                      className="reception-btn reception-btn--primary"
                      onClick={handleConfirmPayment}
                      disabled={confirming}
                    >
                      {confirming ? 'Confirmando…' : 'Confirmar pago'}
                    </button>
                  </div>
                )}
              </div>

              {hasService && (
                <div className="reception-checklist-card">
                  <h3 className="reception-checklist-card__title">Checklist de recepción</h3>
                  <div className="reception-checklist">
                    <div className="reception-checklist-group">
                      <h4 className="reception-checklist-group__title">Verificación de Identidad (Cédula vs. Sistema)</h4>
                      <form
                        className="reception-rut-check"
                        onSubmit={(event) => { event.preventDefault(); handleVerifyRut(); }}
                      >
                        <input
                          type="text"
                          className="search-sample-input"
                          placeholder="RUT de la cédula (12345678-K)"
                          aria-label="RUT de la cédula"
                          value={rutInput}
                          onChange={(event) => { setRutInput(event.target.value); setRutMatches(null); }}
                        />
                        <button type="submit" className="reception-btn reception-btn--ghost" disabled={!rutInput.trim()}>
                          Verificar RUT
                        </button>
                      </form>
                      <label className={`reception-checkbox ${checklist.rut ? 'reception-checkbox--checked' : ''}`}>
                        <input type="checkbox" checked={checklist.rut} readOnly disabled />
                        <div className="reception-checkbox__icon"><CheckSquare size={14} /></div>
                        <span className="reception-checkbox__label">
                          {rutMatches === false ? 'El RUT no coincide' : 'RUT Coincide'}
                        </span>
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
                      onClick={handlePrint}
                      disabled={!sampleCode}
                    >
                      <Printer size={16} /> Imprimir etiqueta
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
};

export default PostloginReception;
