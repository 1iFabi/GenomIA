import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Download, Eye, EyeOff, FileText, KeyRound, LogOut, Pencil, Trash2, UserRound } from 'lucide-react';
import { useSession } from '../../hooks/useSession';
import { useAuthSession } from '../../contexts/AuthContext';
import { usePasswordValidation } from '../../hooks/usePasswordValidation';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { RESULT_MODULES } from '../../config/resultNav';
import DeleteAccountModal from '../../components/DeleteAccountModal/DeleteAccountModal';
import Avatar from './Avatar';
import './Profile.css';

const LOGO = `${import.meta.env.BASE_URL || '/'}cNormal.png`;
const FIGURES = [{ id: 'initial', name: 'Inicial' }, { id: 'helix', name: 'Hélice' }];
const VIEWS = [
  { hash: '', name: 'Mi cuenta', icon: UserRound },
  { hash: 'contrasena', name: 'Contraseña', icon: KeyRound },
  { hash: 'informe', name: 'Informe PDF', icon: FileText },
];
const RULES = [
  ['minLength', '10 caracteres o más'],
  ['hasUppercase', 'Una mayúscula'],
  ['hasNumber', 'Un número'],
  ['hasSymbol', 'Un símbolo'],
];
const RENAME_EVERY_DAYS = 30;

const longDate = (date) => date.toLocaleDateString('es-CL', { day: 'numeric', month: 'long', year: 'numeric' });

const Head = ({ title, sub }) => (
  <header className="me-main__head">
    <h1>{title}</h1>
    <p>{sub}</p>
  </header>
);

/** The username row: read, edit, then confirm, because a rename locks the next one for 30 days. */
const UsernameRow = ({ user, onSaved }) => {
  const [step, setStep] = useState('read');
  const [draft, setDraft] = useState(user.username ?? '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const lockedUntil = user.username_next_change_at ? new Date(user.username_next_change_at) : null;
  const next = draft.trim().toLowerCase();
  const nextFree = new Date(Date.now() + RENAME_EVERY_DAYS * 864e5);

  const close = () => { setStep('read'); setDraft(user.username ?? ''); setError(''); };
  const confirm = async () => {
    setSaving(true);
    const result = await apiRequest(API_ENDPOINTS.ME, { method: 'PATCH', body: JSON.stringify({ username: next }) });
    setSaving(false);
    if (result.ok && result.data?.user) {
      onSaved(result.data.user);
      setStep('read');
    } else {
      setError(result.data?.error || 'No se pudo guardar. Inténtalo de nuevo.');
      setStep('edit');
    }
  };

  return (
    <div className="me-r">
      <dt>Nombre de usuario</dt>
      {step === 'read' && (
        <dd className="me-r__value">
          <span>@{user.username}</span>
          {lockedUntil ? (
            <span className="me-r__note">Podrás cambiarlo el {longDate(lockedUntil)}</span>
          ) : (
            <button type="button" className="me-link" onClick={() => setStep('edit')}>Cambiar</button>
          )}
        </dd>
      )}
      {step === 'edit' && (
        <dd className="me-unfold">
          <form className="me-edit" onSubmit={(e) => { e.preventDefault(); if (next && next !== user.username) setStep('confirm'); }}>
            <label className="me-line-field">
              <span className="me-sr">Nuevo nombre de usuario</span>
              <span className="me-line-field__box">
                <span aria-hidden="true">@</span>
                <input
                  value={draft} maxLength={30} autoFocus autoComplete="username" autoCapitalize="none" spellCheck="false"
                  aria-invalid={error ? 'true' : undefined} aria-describedby="me-username-hint"
                  onChange={(e) => { setDraft(e.target.value); setError(''); }}
                />
              </span>
            </label>
            <div className="me-edit__actions">
              <button type="button" className="me-link" onClick={close}>Cancelar</button>
              <button type="submit" className="me-btn me-btn--primary" disabled={!next || next === user.username}>Continuar</button>
            </div>
          </form>
          <p id="me-username-hint" className={error ? 'me-msg me-msg--error' : 'me-hint'} role={error ? 'alert' : undefined}>
            {error || 'De 3 a 30 caracteres: letras, números, punto, guion o guion bajo. Con él también inicias sesión.'}
          </p>
        </dd>
      )}
      {step === 'confirm' && (
        <dd className="me-unfold me-confirm" role="group" aria-labelledby="me-confirm-q">
          <p id="me-confirm-q" className="me-confirm__q">¿Cambiar tu nombre a <b>@{next}</b>?</p>
          <p className="me-hint">No podrás volver a cambiarlo hasta el {longDate(nextFree)}.</p>
          <div className="me-edit__actions">
            <button type="button" className="me-link" onClick={() => setStep('edit')} disabled={saving}>Volver</button>
            <button type="button" className="me-btn me-btn--primary" onClick={confirm} disabled={saving} autoFocus>
              {saving ? 'Guardando…' : 'Sí, cambiar'}
            </button>
          </div>
        </dd>
      )}
    </div>
  );
};

const SecretField = ({ id, label, value, onChange, autoComplete, describedBy }) => {
  const [shown, setShown] = useState(false);
  return (
    <div className="me-line-field">
      <label className="me-line-field__label" htmlFor={id}>{label}</label>
      <span className="me-line-field__box">
        <input
          id={id} type={shown ? 'text' : 'password'} value={value} autoComplete={autoComplete}
          aria-describedby={describedBy} onChange={(e) => onChange(e.target.value)}
        />
        <button type="button" className="me-eye" onClick={() => setShown((s) => !s)} aria-label={shown ? `Ocultar ${label.toLowerCase()}` : `Mostrar ${label.toLowerCase()}`}>
          {shown ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </button>
      </span>
    </div>
  );
};

/** Change the password in place, the way the reference does it: three underlined fields and one save. */
const PasswordForm = () => {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [state, setState] = useState({ saving: false, error: '', done: false });
  const rules = usePasswordValidation(form.next);
  const strong = Object.values(rules).every(Boolean);
  const matches = form.confirm !== '' && form.next === form.confirm;
  const ready = form.current && strong && matches;
  const set = (key) => (value) => { setForm((f) => ({ ...f, [key]: value })); setState((s) => ({ ...s, error: '', done: false })); };

  const submit = async (e) => {
    e.preventDefault();
    if (!ready) return;
    setState({ saving: true, error: '', done: false });
    const result = await apiRequest(`${API_ENDPOINTS.ME}change-password/`, {
      method: 'POST',
      body: JSON.stringify({ current_password: form.current, new_password: form.next, confirm_password: form.confirm }),
    });
    if (result.ok) {
      setForm({ current: '', next: '', confirm: '' });
      setState({ saving: false, error: '', done: true });
    } else {
      const err = result.data?.error;
      setState({ saving: false, error: (Array.isArray(err) ? err.join(' ') : err) || 'No se pudo cambiar la contraseña.', done: false });
    }
  };

  return (
    <form className="me-pass" onSubmit={submit} noValidate>
      <SecretField id="me-pass-current" label="Contraseña actual" value={form.current} onChange={set('current')} autoComplete="current-password" />
      <SecretField id="me-pass-new" label="Nueva contraseña" value={form.next} onChange={set('next')} autoComplete="new-password" describedBy="me-pass-rules" />
      <ul id="me-pass-rules" className="me-rules" aria-label="Requisitos de la nueva contraseña">
        {RULES.map(([key, text]) => (
          <li key={key} className={rules[key] ? 'is-met' : undefined}>
            <Check aria-hidden="true" />{text}<span className="me-sr">{rules[key] ? ', cumplido' : ', pendiente'}</span>
          </li>
        ))}
      </ul>
      <SecretField id="me-pass-confirm" label="Confirmar nueva contraseña" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" describedBy="me-pass-match" />
      <p id="me-pass-match" className={`me-hint${form.confirm && !matches ? ' me-msg--error' : ''}`}>
        {form.confirm && !matches ? 'No coincide con la nueva contraseña.' : 'Al guardarla se cierran tus sesiones en otros dispositivos.'}
      </p>
      <div className="me-pass__foot">
        <p className={state.error ? 'me-msg me-msg--error' : 'me-msg'} role={state.error ? 'alert' : 'status'}>
          {state.error || (state.done ? 'Contraseña actualizada.' : '')}
        </p>
        <button type="submit" className="me-btn me-btn--primary me-btn--wide" disabled={!ready || state.saving}>
          {state.saving ? 'Guardando…' : 'Guardar cambios'}
        </button>
      </div>
    </form>
  );
};

/**
 * Mi cuenta (/profile): the account card on the left (the logo, the avatar with its edit button, three
 * areas, the way back and sign-out) and the chosen area on the right, picked by the hash. One colour,
 * the brand's blue. The avatar is generated, never a photo.
 */
const Profile = () => {
  const { user, loading } = useSession();
  const { updateUser } = useAuthSession();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const [figure, setFigure] = useState('initial');
  const [avatarState, setAvatarState] = useState({ saving: false, text: '' });
  const [deleting, setDeleting] = useState(false);

  useEffect(() => { if (user) setFigure(user.avatar?.figure || 'initial'); }, [user?.avatar?.figure]);

  if (loading || !user) return null;

  const key = hash.slice(1);
  const view = key === 'avatar' ? 'avatar' : (VIEWS.find((v) => v.hash === key) || VIEWS[0]).hash;
  const firstName = String(user.first_name || user.username || '').split(' ')[0];
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ') || firstName;
  const initial = (firstName || user.email || '?')[0].toUpperCase();
  const savedFigure = user.avatar?.figure || 'initial';

  const saveAvatar = async () => {
    setAvatarState({ saving: true, text: '' });
    const result = await apiRequest(API_ENDPOINTS.ME, {
      method: 'PATCH',
      body: JSON.stringify({ avatar: { color: user.avatar?.color || 'traits', figure } }),
    });
    if (result.ok && result.data?.user) {
      updateUser(result.data.user);
      setAvatarState({ saving: false, text: 'Guardado' });
    } else {
      setAvatarState({ saving: false, text: result.data?.error || 'No se pudo guardar. Inténtalo de nuevo.' });
    }
  };

  const logout = async () => {
    await clearToken();
    window.location.href = '/';
  };

  const views = {
    '': (
      <>
        <Head title="Mi cuenta" sub="Con estos datos entras a GenomIA." />
        <dl className="me-rows">
          <UsernameRow key={user.username} user={user} onSaved={updateUser} />
          <div className="me-r"><dt>Correo</dt><dd className="me-r__value"><span>{user.email}</span></dd></div>
        </dl>
        <div className="me-main__foot">
          <div>
            <p className="me-main__foot-title">Eliminar cuenta</p>
            <p className="me-hint">Se borran tu cuenta y todos tus datos. No se puede deshacer.</p>
          </div>
          <button type="button" className="me-quiet-danger" onClick={() => setDeleting(true)}>
            <Trash2 aria-hidden="true" />Eliminar
          </button>
        </div>
      </>
    ),
    contrasena: (
      <>
        <Head title="Contraseña" sub="Cámbiala cuando quieras." />
        {user.has_password === false
          ? <p className="me-empty">Entras con Google, así que tu contraseña la administra Google.</p>
          : <PasswordForm />}
      </>
    ),
    informe: (
      <>
        <Head title="Informe PDF" sub="Tus cinco módulos en un solo documento." />
        <div className="me-report">
          <figure className="me-doc" aria-hidden="true">
            <div className="me-doc__page">
              <img src={LOGO} alt="" />
              <b>Informe genético</b>
              <span>{fullName}</span>
              <ul>{RESULT_MODULES.map((m) => <li key={m.key}>{m.name}</li>)}</ul>
            </div>
            <div className="me-doc__page me-doc__page--under" />
          </figure>
          <div className="me-report__side">
            <p className="me-report__title">Tu informe completo, listo para guardar o imprimir.</p>
            <p className="me-hint">Incluye {RESULT_MODULES.map((m) => m.name).join(', ').replace(/, ([^,]*)$/, ' y $1')}.</p>
            <button type="button" className="me-btn me-btn--primary me-btn--wide" disabled aria-describedby="me-report-soon">
              <Download aria-hidden="true" />Descargar PDF
            </button>
            <p id="me-report-soon" className="me-msg">La descarga estará disponible pronto.</p>
          </div>
        </div>
      </>
    ),
    avatar: (
      <>
        <Head title="Avatar" sub="Elige cómo te ves en GenomIA. No guardamos fotos tuyas." />
        <fieldset className="me-figures">
          <legend className="me-sr">Figura del avatar</legend>
          {FIGURES.map((f) => (
            <label key={f.id} className="me-figure">
              <input type="radio" name="avatar-figure" value={f.id} checked={figure === f.id} onChange={() => { setFigure(f.id); setAvatarState({ saving: false, text: '' }); }} />
              <Avatar figure={f.id} initial={initial} />
              <span>{f.name}</span>
            </label>
          ))}
        </fieldset>
        <div className="me-pass__foot">
          <p className="me-msg" role="status">{avatarState.text}</p>
          <div className="me-edit__actions">
            <Link className="me-link" to="/profile">Volver</Link>
            <button type="button" className="me-btn me-btn--primary me-btn--wide" disabled={figure === savedFigure || avatarState.saving} onClick={saveAvatar}>
              {avatarState.saving ? 'Guardando…' : 'Guardar avatar'}
            </button>
          </div>
        </div>
      </>
    ),
  };

  return (
    <div className="me">
      <div className="me-shell">
        <aside className="me-side">
          <img className="me-logo" src={LOGO} alt="GenomIA" />
          <div className="me-who">
            <div className="me-who__pic">
              <Avatar figure={view === 'avatar' ? figure : savedFigure} initial={initial} />
              <button type="button" className="me-who__edit" onClick={() => navigate('/profile#avatar')} aria-label="Cambiar avatar">
                <Pencil aria-hidden="true" />
              </button>
            </div>
            <p className="me-who__name">{fullName}</p>
            <p className="me-who__handle">@{user.username}</p>
          </div>
          <nav className="me-nav" aria-label="Tu cuenta">
            {VIEWS.map((v) => {
              const Icon = v.icon;
              return (
                <Link key={v.hash} to={{ pathname: '/profile', hash: v.hash }} className="me-nav__item" aria-current={v.hash === view ? 'page' : undefined}>
                  <Icon aria-hidden="true" />{v.name}
                </Link>
              );
            })}
          </nav>
          <div className="me-side__foot">
            <Link className="me-nav__item" to="/dashboard"><ArrowLeft aria-hidden="true" />Volver a tu ADN</Link>
            <button type="button" className="me-nav__item me-nav__out" onClick={logout}><LogOut aria-hidden="true" />Cerrar sesión</button>
          </div>
        </aside>

        <main className="me-main" key={view}>{views[view]}</main>
      </div>

      <DeleteAccountModal isOpen={deleting} onClose={() => setDeleting(false)} userName={firstName} />
    </div>
  );
};

export default Profile;
