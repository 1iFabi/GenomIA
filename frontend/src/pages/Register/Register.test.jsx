import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import Register from './Register.jsx';

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
// The stepper's own navigation is not under test: expose its final-step callback and render every step.
vi.mock('../../components/Stepper/Stepper.jsx', () => ({
  default: ({ children, onFinalStepCompleted }) => (
    <div>
      {children}
      <button type="button" data-testid="finish" onClick={onFinalStepCompleted}>Finalizar</button>
    </div>
  ),
  Step: ({ children }) => <div>{children}</div>,
}));

let container;
let root;

const render = async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/login" element={<p>login page</p>} />
        </Routes>
      </MemoryRouter>,
    );
  });
};

const type = async (input, value) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
});

const fillAndFinish = async () => {
  await type(document.querySelector('[name="username"]'), 'ana.g');
  await type(document.querySelector('[name="correo"]'), 'Ana@Example.com');
  await type(document.querySelector('[name="contraseña"]'), 'SecurePassword1!');
  await type(document.querySelector('[name="repetirContraseña"]'), 'SecurePassword1!');
  await act(async () => { document.querySelector('[name="terminos"]').click(); });
  await act(async () => { document.querySelector('[data-testid="finish"]').click(); });
};

const dialog = () => document.querySelector('[role="dialog"]');
const resendButton = () => [...document.querySelectorAll('button')].find((b) => /reenviar/i.test(b.textContent));

beforeEach(() => {
  apiRequest.mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  vi.restoreAllMocks();
});

describe('Register', () => {
  it('shows the verification modal after sign-up, with a resend for the address that was used', async () => {
    apiRequest.mockResolvedValueOnce({
      ok: true, status: 201,
      data: { success: true, requires_verification: true, mensaje: 'Debes verificar tu cuenta desde tu correo.' },
    });
    await render();

    await fillAndFinish();

    expect(apiRequest).toHaveBeenCalledWith(API_ENDPOINTS.REGISTER, expect.objectContaining({ method: 'POST' }));
    expect(dialog().textContent).toContain('Debes verificar tu cuenta desde tu correo.');
    apiRequest.mockResolvedValueOnce({ ok: true, status: 200, data: { success: true } });
    await act(async () => { resendButton().click(); });
    expect(apiRequest).toHaveBeenLastCalledWith(API_ENDPOINTS.RESEND_VERIFICATION, {
      method: 'POST',
      body: JSON.stringify({ email: 'ana@example.com' }),
    });
  });

  it('sends the user to the login when the verification modal is dismissed', async () => {
    apiRequest.mockResolvedValueOnce({
      ok: true, status: 201, data: { success: true, requires_verification: true, mensaje: 'Revisa tu correo.' },
    });
    await render();
    await fillAndFinish();

    await act(async () => { [...dialog().querySelectorAll('button')].find((b) => b.textContent === 'Entendido').click(); });

    expect(document.body.textContent).toContain('login page');
  });
});
