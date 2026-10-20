import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Descubre from './Descubre';

// ScrollTrigger registers on import and reads matchMedia then: stub it before any import runs
vi.hoisted(() => {
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
});

let container;
let root;

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.IntersectionObserver = class { observe() {} disconnect() {} unobserve() {} };
  // the atlas is not reachable in tests; the card must still render
  globalThis.fetch = vi.fn(() => Promise.reject(new Error('offline')));
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<Descubre />); });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('Descubre', () => {
  it('presents every module, and Biométricas is gone', () => {
    const titles = [...container.querySelectorAll('.dcard__title')].map((h) => h.textContent);
    expect(titles).toEqual(['Ancestría', 'Farmacogenética', 'Enfermedades', 'Rasgos']);
    expect(container.textContent).not.toMatch(/Biom[eé]tric/);
  });

  it('tells the two risks of Enfermedades in turn, chosen by their tabs', async () => {
    const card = container.querySelector('.dcard--enfermedades');
    expect(card.querySelector('h3').textContent).toBe('Enfermedades');
    expect(card.parentElement.classList.contains('descubre-grid')).toBe(true);
    const tabs = [...card.querySelectorAll('[role="tab"]')];
    expect(tabs.map((t) => t.textContent)).toEqual(['Monogénico', 'Poligénico']);
    expect([...card.querySelectorAll('.risk__name')].map((h) => h.textContent)).toEqual(['Riesgo monogénico', 'Riesgo poligénico']);
    const panels = [...card.querySelectorAll('[role="tabpanel"]')];
    const shown = () => panels.map((p) => p.getAttribute('aria-hidden'));
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(shown()).toEqual(['false', 'true']);
    expect(panels[1].hasAttribute('inert')).toBe(true);

    expect(card.querySelector('.enf__arrows')).toBeNull();
    await act(async () => tabs[1].click());
    expect(tabs[1].getAttribute('aria-selected')).toBe('true');
    expect(shown()).toEqual(['true', 'false']);
    // choosing by hand ends the automatic tour
    expect(card.querySelector('.enf__bar i')).toBeNull();
    await act(async () => tabs[0].click());
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
  });

  it('advances to the next risk when the active bar finishes filling', async () => {
    const card = container.querySelector('.dcard--enfermedades');
    const fill = card.querySelector('.enf__tab[aria-selected="true"] .enf__bar i');
    await act(async () => fill.dispatchEvent(new Event('animationend', { bubbles: true })));
    expect(card.querySelectorAll('[role="tab"]')[1].getAttribute('aria-selected')).toBe('true');
  });

  it('has no call to action of its own: pricing follows right after', () => {
    expect(container.querySelector('a.descubre-cta')).toBeNull();
  });

  it('exposes the globe regions as pressed buttons', async () => {
    const regions = [...container.querySelectorAll('.origins-globe__regions button')];
    expect(regions.map((b) => b.textContent)).toEqual(['América', 'Europa', 'África', 'Asia']);
    expect(regions[0].getAttribute('aria-pressed')).toBe('true');
    await act(async () => regions[2].click());
    expect(regions[2].getAttribute('aria-pressed')).toBe('true');
    expect(regions[0].getAttribute('aria-pressed')).toBe('false');
  });

  it('pairs each trait question with the gene that answers it, one open at a time', async () => {
    const questions = [...container.querySelectorAll('.traits__q')];
    expect(questions.map((q) => q.querySelector('.traits__gene').textContent)).toEqual(['CYP1A2', 'TAS2R38', 'LCT', 'PER3']);
    expect(questions[0].getAttribute('aria-expanded')).toBe('true');
    await act(async () => questions[2].click());
    expect(questions[2].getAttribute('aria-expanded')).toBe('true');
    expect(questions[0].getAttribute('aria-expanded')).toBe('false');
  });

  it('explains each risk in one line, with its picture and a sample result in plain words', () => {
    const monogenic = container.querySelector('.risk--monogenico');
    expect(monogenic.querySelector('.risk__how').textContent).toMatch(/^Un solo cambio que pesa mucho\./);
    expect(monogenic.querySelectorAll('.risk-letters__variant')).toHaveLength(1);
    expect(monogenic.querySelector('.risk__lead').textContent).toBe('Tienes una variante en BRCA2');
    expect(monogenic.querySelector('.risk__meaning').textContent).toMatch(/más alto que el de la mayoría/);
    expect(monogenic.querySelector('.risk__scale')).toBeNull();

    const polygenic = container.querySelector('.risk--poligenico');
    expect(polygenic.querySelector('.risk__how').textContent).toMatch(/^Muchos cambios pequeños que se suman\./);
    expect(polygenic.querySelector('[data-hairline="terrain"]').getAttribute('aria-label')).toMatch(/muchas variantes pequeñas/i);
    expect(polygenic.querySelector('.risk__lead').textContent).toBe('Enfermedad coronaria');
    expect([...polygenic.querySelectorAll('.risk__ticks span')].map((t) => t.textContent)).toEqual(['Más bajo', 'Promedio', 'Más alto']);
    expect(polygenic.querySelector('.risk__track i').style.left).toBe('80%');
  });

  it('explains each risk term in plain words, from a "?" beside its name', async () => {
    const helps = [...container.querySelectorAll('.risk .dcard__head .card-help')];
    expect(helps).toHaveLength(2);
    expect(helps.map((b) => b.querySelector('.card-help__label').textContent)).toEqual([
      'Qué significa riesgo monogénico',
      'Qué significa riesgo poligénico',
    ]);
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull();

    await act(async () => helps[0].dispatchEvent(new FocusEvent('focusin', { bubbles: true })));
    const panel = document.body.querySelector('[role="tooltip"]');
    expect(panel.textContent).toMatch(/un solo gen/i);
    expect(helps[0].getAttribute('aria-describedby')).toBe(panel.id);
  });

  it('takes the tone of the card its "?" sits on: dark over the navy Enfermedades card', async () => {
    const helps = [...container.querySelectorAll('.risk .dcard__head .card-help')];
    // jsdom does not load the stylesheet, so the rows' own colours are set here as they are in the page
    container.querySelector('.dcard--enfermedades').style.background = 'rgb(18, 50, 79)';

    await act(async () => helps[0].dispatchEvent(new FocusEvent('focusin', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]').dataset.tone).toBe('dark');

    await act(async () => helps[0].dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    await act(async () => helps[1].dispatchEvent(new FocusEvent('focusin', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]').dataset.tone).toBe('dark');
  });
});
