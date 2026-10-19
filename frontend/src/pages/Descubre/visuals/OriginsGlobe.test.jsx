import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OriginsGlobe from './OriginsGlobe';

// the atlas is not reachable in tests: an empty world lets the globe become ready without drawing land
const EMPTY_WORLD = { type: 'Topology', arcs: [], objects: { countries: { type: 'GeometryCollection', geometries: [] } } };
const TOUR_MS = 4500;

let container;
let root;
const names = () => [...container.querySelectorAll('.origins-globe__regions button')];
const pressed = () => names().find((b) => b.getAttribute('aria-pressed') === 'true').textContent;

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  // the card reports itself on screen as soon as it mounts, so the tour runs
  globalThis.IntersectionObserver = class {
    constructor(callback) { this.callback = callback; }
    observe() { this.callback([{ isIntersecting: true }]); }
    disconnect() {}
  };
  globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => EMPTY_WORLD }));
  // only the tour's timers are faked; React's own scheduling stays real
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<OriginsGlobe />); });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
});

describe('OriginsGlobe', () => {
  it('moves only on click: hovering or focusing a name leaves the globe where it is', async () => {
    await act(async () => names()[2].dispatchEvent(new Event('pointerover', { bubbles: true })));
    await act(async () => names()[2].dispatchEvent(new FocusEvent('focusin', { bubbles: true })));
    expect(pressed()).toBe('América');
    await act(async () => names()[2].click());
    expect(pressed()).toBe('África');
  });

  it('keeps touring every TOUR_MS on its own, and a click gives its region a full beat', async () => {
    expect(pressed()).toBe('América');
    await act(async () => vi.advanceTimersByTime(TOUR_MS));
    expect(pressed()).toBe('Europa');
    await act(async () => vi.advanceTimersByTime(3000));
    await act(async () => names()[2].click());
    await act(async () => vi.advanceTimersByTime(TOUR_MS - 500));
    expect(pressed()).toBe('África');
    await act(async () => vi.advanceTimersByTime(500));
    expect(pressed()).toBe('Asia');
  });
});
