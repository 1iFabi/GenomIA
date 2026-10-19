import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Conoce from './Conoce';
import { lengthAt, roadThrough } from './route';

// reduced motion: no journey, the route is complete from the start
vi.hoisted(() => {
  window.matchMedia = (q) => ({ matches: q.includes('reduce'), addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
});

let container;
let root;

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.IntersectionObserver = class { observe() {} disconnect() {} unobserve() {} };
  globalThis.ResizeObserver = class { observe() {} disconnect() {} unobserve() {} };
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<Conoce />); });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('Conoce', () => {
  it('shows the four steps in order, all lit, the sample at the last one', () => {
    const steps = [...container.querySelectorAll('ol.conoce-steps > li')];
    expect(steps.map((li) => li.querySelector('h3').textContent)).toEqual([
      'Realiza tu registro en el sistema',
      'Ve al laboratorio a muestrearte',
      'Espera el correo de afirmación',
      'Revisa en la web tus resultados',
    ]);
    expect(steps.every((li) => li.hasAttribute('data-lit'))).toBe(true);
    expect(steps[3].hasAttribute('data-current')).toBe(true);
  });

  it('is not interactive: the mouse does not move the sample', async () => {
    const steps = container.querySelectorAll('ol.conoce-steps > li');
    await act(async () => {
      steps[1].dispatchEvent(Object.assign(new Event('pointerover', { bubbles: true }), { pointerType: 'mouse' }));
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(steps[1].hasAttribute('data-current')).toBe(false);
    expect(steps[3].hasAttribute('data-current')).toBe(true);
  });

  it('winds a road through the stations and measures along it', () => {
    const d = roadThrough([{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 200, y: 0 }]);
    expect(d.startsWith('M 0 0')).toBe(true);
    expect(d.split(' C ')).toHaveLength(3);
    expect(lengthAt([0, 120, 260], 1.5)).toBe(190);
    expect(lengthAt([0, 120, 260], 2)).toBe(260);
  });
});
