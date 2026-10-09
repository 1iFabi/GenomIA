import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../config/api';
import NoPurchased from './NoPurchased';
import PurchaseEmailNotice from '../../components/PurchaseEmailNotice/PurchaseEmailNotice';

let mockUser;

vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: mockUser }) }));
vi.mock('../../config/api', () => ({
  API_ENDPOINTS: { PURCHASE_PROFILE: '/purchase-profile' },
  apiRequest: vi.fn(),
  clearToken: vi.fn(),
  refreshSession: vi.fn(),
}));

let container;
let root;

const renderPage = async (user) => {
  mockUser = user;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/no-purchased']}>
        <Routes>
          <Route path="/no-purchased" element={<NoPurchased />} />
          <Route path="/" element={<><PurchaseEmailNotice /><main data-testid="landing" /></>} />
        </Routes>
      </MemoryRouter>
    );
  });
  return container;
};

const typeInto = async (input, value) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  await act(async () => {
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};
const openPurchase = async () => {
  const view = await renderPage({ first_name: 'Ana', email: 'ana@example.com', purchase_profile_complete: false });
  const button = [...view.querySelectorAll('button')].find((item) => item.textContent === 'Adquirir servicio');
  await act(async () => button.click());
  return view;
};

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
  vi.clearAllMocks();
});

describe('NoPurchased', () => {
  it('tells the client the Sample ID arrives by email after the purchase, without a button once data is complete', async () => {
    const view = await renderPage({ first_name: 'Ana', email: 'ana@example.com', purchase_profile_complete: true });
    expect(view.querySelector('.content-title').textContent).toBe('¿Cómo realizar tu examen?');
    expect(view.querySelectorAll('.step-value')[2].textContent)
      .toBe('Te entregaremos tu Sample ID por correo cuando completes la compra');
    expect(view.querySelector('.split-logo').getAttribute('src')).toContain('cNormal.png');
    expect(view.querySelector('.purchase-submit')).toBeNull();
  });

  it('turns the whole steps panel into the purchase form and returns focus on Volver', async () => {
    const view = await openPurchase();
    expect(view.querySelector('.steps-list')).toBeNull();
    expect(view.querySelector('#purchase-rut')).not.toBeNull();
    expect(document.activeElement).toBe(view.querySelector('#purchase-title'));

    const back = [...view.querySelectorAll('button')].find((item) => item.textContent.includes('Volver'));
    await act(async () => back.click());
    expect(view.querySelectorAll('.step-value')).toHaveLength(3);
    expect(document.activeElement.textContent).toBe('Adquirir servicio');
  });
});

describe('PurchaseProfileForm', () => {
  it('asks for full names and surnames capped at 30 characters', async () => {
    const view = await openPurchase();
    const nombres = view.querySelector('#purchase-nombre');
    expect(view.querySelector('label[for="purchase-nombre"]').textContent).toBe('Nombres');
    expect(view.querySelector('label[for="purchase-apellido"]').textContent).toBe('Apellidos');
    expect(nombres.getAttribute('maxLength')).toBe('30');
    await typeInto(nombres, 'M'.repeat(40));
    expect(nombres.value).toHaveLength(30);
  });

  it('takes the RUT without dots and with dash, without auto-formatting, and caps the phone at 8 digits', async () => {
    const view = await openPurchase();
    const rut = view.querySelector('#purchase-rut');
    expect(rut.getAttribute('placeholder')).toBe('12345678-5');
    await typeInto(rut, '12.345.678-k');
    expect(rut.value).toBe('12345678-K');
    await typeInto(rut, '123456785');
    expect(rut.value).toBe('123456785');
    await act(async () => view.querySelector('form').requestSubmit());
    expect(view.querySelector('#purchase-rut-error').textContent).toBe('Escribe tu RUT sin puntos y con guion (ej: 12345678-5)');
    const phone = view.querySelector('#purchase-telefono');
    await typeInto(phone, '9 8765-43210');
    expect(phone.value).toBe('98765432');
  });

  it('offers Sexo as a select with Femenino, Masculino or Otro and no helper hints', async () => {
    const view = await openPurchase();
    expect(view.querySelector('label[for="purchase-sexoAlNacer"]').textContent).toBe('Sexo');
    expect([...view.querySelectorAll('#purchase-sexoAlNacer option')].map((option) => [option.value, option.textContent]))
      .toEqual([['', 'Selecciona…'], ['female', 'Femenino'], ['male', 'Masculino'], ['other', 'Otro']]);
    expect(view.querySelector('.purchase-phone span').textContent).toBe('+569');
    expect(view.querySelector('.purchase-field__hint')).toBeNull();
    expect(view.querySelector('form').textContent).not.toMatch(/Paterno y materno|Hasta 30|Escribe solo/);
  });

  it('takes the birth year typed as at most four digits, with no picker', async () => {
    const view = await openPurchase();
    const year = view.querySelector('#purchase-anioNacimiento');
    expect(view.querySelector('label[for="purchase-anioNacimiento"]').textContent).toBe('Año de nacimiento');
    expect(year.tagName).toBe('INPUT');
    expect(year.getAttribute('maxLength')).toBe('4');
    await typeInto(year, '19a96-07');
    expect(year.value).toBe('1996');
    await typeInto(year, '3000');
    await act(async () => view.querySelector('form').requestSubmit());
    expect(view.querySelector('#purchase-anioNacimiento-error').textContent)
      .toBe(`Escribe un año entre 1900 y ${new Date().getFullYear()}`);
    expect(view.querySelector('[role="dialog"]')).toBeNull();
  });

  it('centers the Adquirir servicio button under the steps', async () => {
    const view = await renderPage({ first_name: 'Ana', email: 'ana@example.com', purchase_profile_complete: false });
    const button = [...view.querySelectorAll('button')].find((item) => item.textContent === 'Adquirir servicio');
    expect(button.classList.contains('purchase-start')).toBe(true);
  });

  it('submits normalized data with the chosen sex and birth year', async () => {
    apiRequest.mockResolvedValue({ ok: true, data: { emailSent: true } });
    const view = await openPurchase();
    await typeInto(view.querySelector('#purchase-apellido'), 'González Pérez');
    await typeInto(view.querySelector('#purchase-rut'), '12345678-5');
    await typeInto(view.querySelector('#purchase-telefono'), '12345678');
    const sexo = view.querySelector('#purchase-sexoAlNacer');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set.call(sexo, 'other');
      sexo.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await typeInto(view.querySelector('#purchase-anioNacimiento'), '1996');
    await act(async () => view.querySelector('form').requestSubmit());
    expect(JSON.parse(apiRequest.mock.calls[0][1].body)).toEqual({
      nombre: 'Ana', apellido: 'González Pérez', rut: '12345678-5', telefono: '+56912345678',
      sexoAlNacer: 'other', anioNacimiento: 1996,
    });
    expect(view.querySelector('[data-testid="landing"]')).not.toBeNull();
    const dialog = view.querySelector('[role="dialog"]');
    expect(dialog.querySelector('.modal-title').textContent).toBe('Revisa tu correo');
    expect(dialog.textContent).toContain('Te enviamos tu Sample ID a ana@example.com');
  });
});
