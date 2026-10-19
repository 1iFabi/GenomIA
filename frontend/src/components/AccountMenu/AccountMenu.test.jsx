import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import AccountMenu from './AccountMenu';
import { GenominProvider, useGenomin } from '../../context/GenominContext';

let container;
let root;

const Probe = () => <p data-testid="genomin">{useGenomin().open ? 'open' : 'closed'}</p>;

const mount = async (ui) => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<MemoryRouter>{ui}</MemoryRouter>));
  await act(async () => container.querySelector('.acct__toggle').click());
  return [...container.querySelectorAll('.acct__item')];
};

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

it('opens Genomin from the menu, and leaves the item out without its provider', async () => {
  let items = await mount(<GenominProvider><AccountMenu /><Probe /></GenominProvider>);
  const ask = items.find((el) => el.textContent === 'Pregúntale a Genomin');
  await act(async () => ask.click());
  expect(container.querySelector('[data-testid="genomin"]').textContent).toBe('open');
  expect(container.querySelector('.acct__pop')).toBeNull();
  await act(async () => root.unmount());
  container.remove();

  items = await mount(<AccountMenu />);
  expect(items.map((el) => el.textContent)).not.toContain('Pregúntale a Genomin');
});
