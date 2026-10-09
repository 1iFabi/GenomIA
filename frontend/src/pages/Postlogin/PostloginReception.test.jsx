import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PostloginReception from './PostloginReception';
import { apiRequest } from '../../config/api';

vi.mock('../../config/api', () => ({
  API_ENDPOINTS: { RECEPTION_SEARCH: '/search', CONFIRM_PAYMENT: '/payments', RECEPTION_VERIFY_RUT: '/verify-rut' },
  apiRequest: vi.fn(),
  clearToken: vi.fn(),
}));
vi.mock('../../components/AdminSidebar/AdminSidebar', () => ({ default: () => <nav /> }));

const client = {
  user_id: 7, first_name: 'Ana', last_name: 'Pérez', client_code: 'GX-ABCD1234',
  service_status: 'NO_PURCHASED', service_request_status: null, service_samples: [],
};
const paid = {
  ...client, service_status: 'PENDING', service_request_status: 'WAITING_SAMPLE',
  service_samples: [{ sample_code: 'GX-ABCD1234', status: 'pending_collection' }],
};

let container;
let root;

const render = async () => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<MemoryRouter><PostloginReception user={{ first_name: 'Rita' }} /></MemoryRouter>));
};

const typeInto = async (input, value) => {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};

const searchFor = async (value) => {
  await typeInto(container.querySelector('.search-sample-input'), value);
  await act(async () => container.querySelector('.search-sample-form').requestSubmit());
};

const button = (label) => [...container.querySelectorAll('button')].find((node) => node.textContent === label);

beforeEach(() => apiRequest.mockReset());
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('reception', () => {
  it('searches only by Sample ID, confirms payment and never shows personal contact data', async () => {
    apiRequest
      .mockResolvedValueOnce({ ok: true, data: { results: [client] } })
      .mockResolvedValueOnce({ ok: true, data: { sampleCode: 'GX-ABCD1234', sampleEmailSent: true } })
      .mockResolvedValueOnce({ ok: true, data: { results: [paid] } });
    await render();
    await searchFor(' ana@example.com ');
    expect(apiRequest).toHaveBeenLastCalledWith('/search?sample_code=ana%40example.com', { method: 'GET' });
    expect(container.querySelector('.reception-user-card__code').textContent).toBe('GX-ABCD1234');
    expect(container.textContent).toContain('Sin servicio');
    expect(container.textContent).not.toMatch(/Correo|RUT$/m);
    expect(container.textContent).not.toContain('Checklist de recepción');

    await act(async () => button('Confirmar pago').click());
    expect(apiRequest).toHaveBeenNthCalledWith(2, '/payments', { method: 'POST', body: JSON.stringify({ userId: 7 }) });
    expect(apiRequest).toHaveBeenLastCalledWith('/search?sample_code=GX-ABCD1234', { method: 'GET' });
    expect(container.textContent).toContain('Sample ID GX-ABCD1234 enviado al correo del cliente');
    expect(container.textContent).toContain('Esperando muestra');
    expect(button('Confirmar pago')).toBeUndefined();
    expect(container.textContent).toContain('Checklist de recepción');
  });

  it('verifies the typed RUT without ever receiving it and reports a failed email', async () => {
    apiRequest
      .mockResolvedValueOnce({ ok: true, data: { results: [client] } })
      .mockResolvedValueOnce({ ok: true, data: { sampleCode: 'GX-ABCD1234', sampleEmailSent: false } })
      .mockResolvedValueOnce({ ok: true, data: { results: [paid] } });
    await render();
    await searchFor('GX-ABCD1234');
    await act(async () => button('Confirmar pago').click());
    expect(container.textContent).toContain('No se pudo enviar el correo: entrégaselo al cliente.');

    const rutInput = container.querySelector('input[aria-label="RUT de la cédula"]');
    const rutCheckbox = () => container.querySelector('.reception-checkbox input');
    apiRequest.mockResolvedValueOnce({ ok: true, data: { matches: false } });
    await typeInto(rutInput, '12345678-9');
    await act(async () => container.querySelector('.reception-rut-check').requestSubmit());
    expect(apiRequest).toHaveBeenLastCalledWith('/verify-rut', {
      method: 'POST', body: JSON.stringify({ userId: 7, rut: '12345678-9' }),
    });
    expect(container.textContent).toContain('El RUT no coincide');
    expect(rutCheckbox().checked).toBe(false);

    apiRequest.mockResolvedValueOnce({ ok: true, data: { matches: true } });
    await typeInto(rutInput, '12345678-K');
    await act(async () => container.querySelector('.reception-rut-check').requestSubmit());
    expect(rutCheckbox().checked).toBe(true);
    expect(rutCheckbox().disabled).toBe(true);
  });
  it('shows result-shaped placeholders without a spinning search icon while lookup is pending', async () => {
    let resolveSearch;
    apiRequest.mockReturnValue(new Promise((resolve) => { resolveSearch = resolve; }));
    await render();
    await typeInto(container.querySelector('.search-sample-input'), 'GX-ABCD1234');
    act(() => container.querySelector('.search-sample-form').requestSubmit());
    expect(container.querySelector('.search-sample-button').disabled).toBe(true);
    expect(container.querySelector('.search-sample-button').textContent).toBe('Buscar');
    expect(container.querySelector('[role="status"]')?.textContent).toContain('Buscando muestra');
    expect(container.querySelectorAll('.reception-skeleton')).toHaveLength(2);
    expect(container.querySelectorAll('.reception-skeleton__check-row')).toHaveLength(6);
    expect(container.querySelector('.loader-spinner, .spin')).toBeNull();
    await act(async () => resolveSearch({ ok: true, data: { results: [] } }));
  });

});
