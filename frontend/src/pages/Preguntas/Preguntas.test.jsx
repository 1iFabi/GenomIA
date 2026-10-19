import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Preguntas from './Preguntas';

// ScrollTrigger registers on import and reads matchMedia then: stub it before any import runs
vi.hoisted(() => {
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
});

let container;
let root;

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<Preguntas />); });
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  container.remove();
});

const preguntas = () => [...container.querySelectorAll('.faq-q')];
const click = (el) => act(async () => { el.click(); });

describe('Preguntas', () => {
  it('muestra 5 y revela el resto con "Ver más"', async () => {
    expect(preguntas()).toHaveLength(5);
    await click(container.querySelector('button.faq-link'));
    expect(preguntas()).toHaveLength(8);
    expect(container.querySelector('button.faq-link')).toBeNull();
  });

  it('abre una pregunta a la vez', async () => {
    const [a, b] = preguntas();
    await click(a);
    expect(a.getAttribute('aria-expanded')).toBe('true');
    await click(b);
    expect(a.getAttribute('aria-expanded')).toBe('false');
    expect(b.getAttribute('aria-expanded')).toBe('true');
    await click(b);
    expect(b.getAttribute('aria-expanded')).toBe('false');
  });
});
