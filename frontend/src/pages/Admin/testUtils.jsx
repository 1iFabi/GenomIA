import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

// Mount an admin page in a router; returns the container. Call unmountPage() in afterEach.
let root;
let container;

export const mountPage = async (ui, at = '/dashboard') => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<MemoryRouter initialEntries={[at]}>{ui}</MemoryRouter>));
  return container;
};

export const unmountPage = async () => {
  await act(async () => root.unmount());
  container.remove();
};

export const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
