import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import GoogleSignup from './GoogleSignup.jsx';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(),
  apiRequest: vi.fn(),
}));
vi.mock('../../components/AuthPlate/AuthPlate.jsx', () => ({ default: () => null }));
vi.mock('../../components/TermsModal/TermsModal.jsx', () => ({ default: () => null }));

let container;
let root;

const render = async (state = { pending: 'signed-token', email: 'ana@gmail.com' }) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[{ pathname: '/register/google', state }]}>
        <Routes>
          <Route path="/register/google" element={<GoogleSignup />} />
          <Route path="/dashboard" element={<p>dashboard</p>} />
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
const submit = async () => act(async () => {
  document.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
const acceptTerms = async () => act(async () => { document.querySelector('input[type="checkbox"]').click(); });

beforeEach(() => apiRequest.mockReset());

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

describe('GoogleSignup', () => {
  it('goes back to the login when there is no Google token to complete', async () => {
    await render({});
    expect(document.body.textContent).toContain('login page');
  });

  it('creates nothing and stays put until a valid username and the terms are given', async () => {
    await render();

    await submit();
    await type(document.querySelector('#google-username'), 'ana.g');
    await submit();

    expect(apiRequest).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('Debes aceptar los términos y condiciones');
    expect(document.body.textContent).not.toContain('dashboard');
  });

  it('opens the dashboard only after the server accepts the username and terms', async () => {
    apiRequest.mockResolvedValueOnce({ ok: true, status: 201, data: { success: true } });
    await render();
    await type(document.querySelector('#google-username'), ' Ana.G ');
    await acceptTerms();

    await submit();

    expect(apiRequest).toHaveBeenCalledWith(API_ENDPOINTS.GOOGLE_COMPLETE, {
      method: 'POST',
      body: JSON.stringify({ pending: 'signed-token', username: 'ana.g', terminos: true }),
    });
    expect(document.body.textContent).toContain('dashboard');
  });

  it('stays on the form when the server refuses', async () => {
    apiRequest.mockResolvedValueOnce({ ok: false, status: 400, data: { error: 'Este nombre de usuario ya está registrado' } });
    await render();
    await type(document.querySelector('#google-username'), 'taken');
    await acceptTerms();

    await submit();

    expect(document.body.textContent).toContain('Este nombre de usuario ya está registrado');
    expect(document.body.textContent).not.toContain('dashboard');
  });
});
