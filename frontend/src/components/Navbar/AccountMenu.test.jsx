import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AccountMenu from './AccountMenu';

vi.mock('../../config/api', () => ({ clearToken: vi.fn() }));

let container;
let root;

// Radix abre el menú con Enter: no depende de eventos de puntero en jsdom.
const openMenu = async (user) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <AccountMenu user={user} theme="light" />
      </MemoryRouter>
    );
  });
  await act(async () => {
    container.querySelector('.account-trigger').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })
    );
  });
  return [...document.querySelectorAll('[role="menuitem"]')].map((item) => item.textContent.trim());
};

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
});

describe('AccountMenu', () => {
  it.each([
    ['client without service', { email: 'ana@example.com', service_status: 'NO_PURCHASED' }, ['Adquirir servicio', 'Cerrar sesión']],
    ['client with service', { email: 'ana@example.com', service_status: 'COMPLETED' }, ['Perfil', 'Ir al dashboard', 'Cerrar sesión']],
    ['staff without service', { email: 'root@example.com', is_staff: true, service_status: 'NO_PURCHASED' }, ['Perfil', 'Ir al dashboard', 'Cerrar sesión']],
  ])('lists the right items for %s', async (_name, user, labels) => {
    expect(await openMenu(user)).toEqual(labels);
  });
});
