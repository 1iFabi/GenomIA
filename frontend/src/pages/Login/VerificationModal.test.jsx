import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import VerificationModal from './VerificationModal.jsx';

vi.mock('../../config/api', async (importOriginal) => ({
  ...await importOriginal(),
  apiRequest: vi.fn(),
}));

let container;
let root;

const render = async (props = {}) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<VerificationModal isOpen onClose={() => {}} message="Revisa tu correo." {...props} />);
  });
};

const resendButton = () => [...document.querySelectorAll('button')].find((b) => /reenviar/i.test(b.textContent));
const click = async (element) => act(async () => { element.click(); });

beforeEach(() => {
  vi.useFakeTimers();
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({ ok: true, status: 200, data: { success: true } });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  vi.useRealTimers();
});

describe('VerificationModal resend', () => {
  it('offers no resend when there is no address to resend to', async () => {
    await render();
    expect(resendButton()).toBeUndefined();
  });

  it('asks the server for a new link and answers with a message that reveals nothing', async () => {
    await render({ resendEmail: 'ana@example.com' });

    await click(resendButton());

    expect(apiRequest).toHaveBeenCalledWith(API_ENDPOINTS.RESEND_VERIFICATION, {
      method: 'POST',
      body: JSON.stringify({ email: 'ana@example.com' }),
    });
    expect(document.body.textContent).toContain('Si el correo está pendiente de verificación, te enviamos un nuevo enlace.');
  });

  it('blocks another resend for 60 seconds', async () => {
    await render({ resendEmail: 'ana@example.com' });
    await click(resendButton());

    expect(resendButton().disabled).toBe(true);
    expect(resendButton().textContent).toContain('60');
    await act(async () => { vi.advanceTimersByTime(59_000); });
    expect(resendButton().disabled).toBe(true);
    await act(async () => { vi.advanceTimersByTime(1_000); });
    expect(resendButton().disabled).toBe(false);

    await click(resendButton());
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it('tells the user to wait when the server throttles the resend', async () => {
    apiRequest.mockResolvedValue({ ok: false, status: 429, data: {} });
    await render({ resendEmail: 'ana@example.com' });

    await click(resendButton());

    expect(document.body.textContent).toContain('Espera un momento antes de pedir otro correo.');
  });

  it('reports a failed request without claiming the mail was sent', async () => {
    apiRequest.mockResolvedValue({ ok: false, status: 0, data: { error: 'Error de conexión con el servidor' } });
    await render({ resendEmail: 'ana@example.com' });

    await click(resendButton());

    expect(document.body.textContent).toContain('No pudimos reenviar el correo. Inténtalo nuevamente.');
    expect(document.body.textContent).not.toContain('te enviamos un nuevo enlace');
  });
});
