import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { apiRequest } from '../../config/api';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(),
  apiRequest: vi.fn(),
}));

let container;
let root;
let googleCallback;

function Pending() {
  const { state } = useLocation();
  return <p>pending:{state.pending}:{state.email}</p>;
}

const render = async (props = {}) => {
  vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id');
  vi.resetModules();
  const { default: GoogleAuthButton } = await import('./GoogleAuthButton.jsx');
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<GoogleAuthButton {...props} />} />
          <Route path="/register/google" element={<Pending />} />
          <Route path="/dashboard" element={<p>dashboard</p>} />
        </Routes>
      </MemoryRouter>,
    );
  });
};

const signInWithGoogle = async () => {
  await act(async () => {
    await googleCallback({ credential: 'id-token' });
  });
};

beforeEach(() => {
  window.google = {
    accounts: {
      id: {
        initialize: vi.fn(({ callback }) => { googleCallback = callback; }),
        renderButton: vi.fn(),
      },
    },
  };
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  delete window.google;
  vi.unstubAllEnvs();
  vi.mocked(apiRequest).mockReset();
});

describe('GoogleAuthButton', () => {
  it('renders the official Google button with our client id', async () => {
    await render();
    expect(window.google.accounts.id.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: 'test-client-id' }),
    );
    expect(window.google.accounts.id.renderButton).toHaveBeenCalled();
  });

  it('sends new Google users to pick a username', async () => {
    vi.mocked(apiRequest).mockResolvedValue({
      ok: true, status: 200, data: { needs_username: true, pending: 'signed', email: 'ana@gmail.com' },
    });
    await render();
    await signInWithGoogle();
    expect(vi.mocked(apiRequest).mock.calls[0][1].body).toBe(JSON.stringify({ credential: 'id-token' }));
    expect(container.textContent).toBe('pending:signed:ana@gmail.com');
  });

  it('logs linked users in and shows backend errors otherwise', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({
      ok: false, status: 409, data: { error: 'Ya existe una cuenta con este correo.' },
    });
    await render();
    await signInWithGoogle();
    expect(container.querySelector('[role="alert"]').textContent).toBe('Ya existe una cuenta con este correo.');

    vi.mocked(apiRequest).mockResolvedValueOnce({ ok: true, status: 200, data: { success: true } });
    await signInWithGoogle();
    expect(container.textContent).toBe('dashboard');
  });

  it('tells the backend when it is used to sign up, so an existing account is refused instead of opened', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({
      ok: false, status: 409, data: { error: 'Ya existe una cuenta con este correo.' },
    });
    await render({ intent: 'signup', text: 'signup_with' });
    await signInWithGoogle();
    expect(JSON.parse(vi.mocked(apiRequest).mock.calls[0][1].body)).toEqual({ credential: 'id-token', intent: 'signup' });
    expect(container.querySelector('[role="alert"]').textContent).toBe('Ya existe una cuenta con este correo.');
  });
});
