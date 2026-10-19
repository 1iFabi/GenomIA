import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import GenomaPricing from './GenomaPricing';

// ScrollTrigger registers on import and reads matchMedia then: stub it before any import runs
vi.hoisted(() => {
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
});

let container;
let root;

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  // jsdom has no canvas: the helix keeps its poster frame
  HTMLCanvasElement.prototype.getContext = () => null;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><GenomaPricing /></MemoryRouter>); });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('GenomaPricing', () => {
  it('names the package, and states the price as real text for every reader', () => {
    expect(container.querySelector('h2').textContent).toBe('GenomIA.vcf');
    expect(container.querySelector('.gp-sr').textContent).toBe('300.000 pesos chilenos');
    expect(container.querySelector('.gp-price__figure').getAttribute('aria-hidden')).toBe('true');
    expect(container.querySelector('.gp-stage').getAttribute('aria-hidden')).toBe('true');
  });

  it('decodes from DNA bases before the sheet is in view, and settles on unmount', async () => {
    const digits = [...container.querySelectorAll('.gp-digit')];
    expect(digits.map((d) => d.dataset.d).join('')).toBe('300000');
    expect(digits.every((d) => 'ACGT'.includes(d.textContent))).toBe(true);
    await act(async () => root.unmount());
    expect(digits.map((d) => d.textContent).join('')).toBe('300000');
    root = createRoot(container); // afterEach unmounts again
  });

  it('keeps the one action on /register', () => {
    const links = container.querySelectorAll('a');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('href')).toBe('/register');
  });
});
