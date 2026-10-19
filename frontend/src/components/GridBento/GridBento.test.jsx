import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import GridBento from './GridBento';

let container;
let root;

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
  vi.unstubAllGlobals();
});

describe('GridBento internal CTA', () => {
  it('renders the CTA as a link to its route and runs its onClick', async () => {
    const onClick = vi.fn();
    const cards = [{
      id: 'postlogin-ancestria',
      title: 'Ancestría',
      description: 'Descripción de prueba.',
      cta: { label: 'Explorar ahora', href: '/dashboard/ancestria', ariaLabel: 'Explorar Ancestría', onClick },
    }];
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route path="/dashboard" element={<GridBento cards={cards} enableStars={false} enableSpotlight={false} />} />
            <Route path="/dashboard/ancestria" element={<p>Página de Ancestría</p>} />
          </Routes>
        </MemoryRouter>,
      );
    });

    const link = container.querySelector('a.card__cta');
    expect(link.getAttribute('href')).toBe('/dashboard/ancestria');

    await act(async () => link.click());

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain('Página de Ancestría');
  });
});
