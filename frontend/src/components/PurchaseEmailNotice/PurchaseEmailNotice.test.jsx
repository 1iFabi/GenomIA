import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import PurchaseEmailNotice from './PurchaseEmailNotice';

let root;
let container;
let location;
const LocationProbe = () => {
  location = useLocation();
  return null;
};
const renderNotice = async (state) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={[{ pathname: '/', state }]}>
      <PurchaseEmailNotice />
      <LocationProbe />
    </MemoryRouter>
  ));
  return container;
};

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('PurchaseEmailNotice', () => {
  it('renders nothing on a normal visit to the landing', async () => {
    const view = await renderNotice(null);
    expect(view.querySelector('[role="dialog"]')).toBeNull();
  });

  it('asks to check the email and clears the notice when closed', async () => {
    const view = await renderNotice({ purchaseEmail: { sent: true, email: 'ana@example.com' } });
    const dialog = view.querySelector('[role="dialog"]');
    expect(dialog.querySelector('.modal-title').textContent).toBe('Revisa tu correo');
    expect(dialog.textContent).toContain('Te enviamos tu Sample ID a ana@example.com');
    await act(async () => [...dialog.querySelectorAll('button')].find((button) => button.textContent === 'Entendido').click());
    expect(view.querySelector('[role="dialog"]')).toBeNull();
    expect(location.state).toBeNull();
  });

  it('says how to get help when the email could not be sent', async () => {
    const view = await renderNotice({ purchaseEmail: { sent: false, email: 'ana@example.com' } });
    expect(view.querySelector('.modal-title').textContent).toBe('Tus datos quedaron registrados');
    expect(view.textContent).toContain('no pudimos enviar el correo');
  });
});
