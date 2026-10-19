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
  it('presents the five modules, and Biométricas is gone', () => {
    const titles = [...container.querySelectorAll('.dcard__title')].map((h) => h.textContent);
    expect(titles).toEqual(['Ancestría', 'Farmacogenética', 'Riesgo monogénico', 'Riesgo poligénico', 'Rasgos']);
    expect(container.textContent).not.toMatch(/Biom[eé]tric/);
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

  it('answers each health module with a figure and a sample result, labelled as an example', () => {
    for (const id of ['farmacogenetica', 'monogenico', 'poligenico']) {
      const card = container.querySelector(`.dcard--${id}`);
      expect(card.querySelector('[data-hairline]').getAttribute('aria-label')).toBeTruthy();
      expect(card.querySelector('.example__label').textContent).toBe('Ejemplo de resultado');
    }
    expect(container.querySelector('.dcard--monogenico .example__lead').textContent).toBe('BRCA2');
    // Rasgos has no figure: its questions carry the card
    expect(container.querySelector('.dcard--rasgos [data-hairline]')).toBeNull();
  });

  it('explains each risk term in plain words, from a "?" beside its title', async () => {
    const helps = [...container.querySelectorAll('.dcard__head .card-help')];
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

  it('takes the tone of the card its "?" sits on: dark over the navy card, light over the white ones', async () => {
    const helps = [...container.querySelectorAll('.dcard__head .card-help')];
    // jsdom does not load the stylesheet, so the cards' own colours are set here as they are in the page
    container.querySelector('.dcard--monogenico').style.background = 'rgb(18, 50, 79)';
    container.querySelector('.dcard--poligenico').style.background = 'rgba(255, 255, 255, 0.78)';

    await act(async () => helps[0].dispatchEvent(new FocusEvent('focusin', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]').dataset.tone).toBe('dark');

    await act(async () => helps[0].dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    await act(async () => helps[1].dispatchEvent(new FocusEvent('focusin', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]').dataset.tone).toBe('light');
  });
});
