import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import Login from './Login.jsx';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(),
  apiRequest: vi.fn(),
}));
vi.mock('../../components/AuthPlate/AuthPlate.jsx', () => ({ default: () => null }));
vi.mock('../../components/GoogleAuthButton/GoogleAuthButton.jsx', () => ({
  default: () => null,
  AuthDivider: ({ children }) => <div>{children}</div>,
}));
vi.mock('../../lib/authPanelSwap', () => ({
  openAuthPanel: vi.fn(),
  playAuthPageEntrance: vi.fn(),
  playAuthPlateEntry: vi.fn(),
  readAuthPanelSwap: () => null,
}));

const UNVERIFIED = 'Tu cuenta aún no ha sido verificada. Revisa tu correo para completar la verificación.';

let container;
let root;

const render = async (path = '/login') => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<p>dashboard</p>} />
        </Routes>
      </MemoryRouter>,
    );
  });
};

const type = async (input, value) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
});

const submitLogin = async (email = 'ana@example.com') => {
  await type(document.querySelector('#login-email'), email);
  await type(document.querySelector('#login-password'), 'Secret-pass-1!');
  await act(async () => {
    document.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });
};

const dialog = () => document.querySelector('[role="dialog"]');
const resendButton = () => [...document.querySelectorAll('button')].find((b) => /reenviar/i.test(b.textContent));

beforeEach(() => {
  apiRequest.mockReset();
  vi.spyOn(console, 'log').mockImplementation(() => {});
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  vi.restoreAllMocks();
});

describe('Login with an unverified account', () => {
  beforeEach(() => {
    apiRequest.mockResolvedValueOnce({
      ok: false, status: 400, data: { error: UNVERIFIED, requires_verification: true },
    });
  });

  it('shows the verification modal with the server message instead of field errors', async () => {
    await render();
    await submitLogin();

    expect(dialog()).not.toBeNull();
    expect(dialog().textContent).toContain(UNVERIFIED);
    expect(document.querySelectorAll('.has-error')).toHaveLength(0);
    expect(document.querySelector('#login-email').getAttribute('aria-invalid')).toBe('false');
    expect(document.querySelector('#login-password').getAttribute('aria-invalid')).toBe('false');
  });

  it('resends to the address that was typed', async () => {
    await render();
    await submitLogin('Ana@Example.com');
    apiRequest.mockResolvedValueOnce({ ok: true, status: 200, data: { success: true } });

    await act(async () => { resendButton().click(); });

    expect(apiRequest).toHaveBeenLastCalledWith(API_ENDPOINTS.RESEND_VERIFICATION, {
      method: 'POST',
      body: JSON.stringify({ email: 'ana@example.com' }),
    });
  });

  it('offers the resend only for this failure, not for the verified-account notice', async () => {
    await render('/login?verified=1');

    expect(dialog().textContent).toContain('Tu cuenta fue verificada correctamente');
    expect(resendButton()).toBeUndefined();
  });
});

describe('Login session', () => {
  it('has no "remember my account" option and asks the server for a plain session', async () => {
    apiRequest.mockResolvedValueOnce({ ok: true, status: 200, data: { success: true } });
    await render();

    expect(document.body.textContent).not.toContain('Recordar mi cuenta');
    expect(document.querySelector('input[type="checkbox"]')).toBeNull();

    vi.useFakeTimers();
    await submitLogin();
    vi.useRealTimers();

    expect(apiRequest).toHaveBeenCalledWith(API_ENDPOINTS.LOGIN, {
      method: 'POST',
      body: JSON.stringify({ username: 'ana@example.com', password: 'Secret-pass-1!' }),
    });
  });
});

describe('Login with wrong credentials', () => {
  it('still marks both fields', async () => {
    apiRequest.mockResolvedValueOnce({
      ok: false, status: 400, data: { success: false, error: 'Credenciales inválidas' },
    });
    await render();
    await submitLogin();

    expect(document.querySelectorAll('.has-error')).toHaveLength(2);
    expect(dialog()).toBeNull();
  });
});
