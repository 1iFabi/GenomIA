import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  armAuthPanelSwap,
  openAuthPanel,
  playAuthPageEntrance,
  playAuthPlateEntry,
  readAuthPanelSwap,
  resetAuthPanelSwap,
  resolveAuthPlateMotion,
} from './authPanelSwap';

const buildPlates = () => {
  const root = document.createElement('div');
  root.className = 'auth';
  root.innerHTML = `
    <section class="auth-left">
      <div class="left-inner">
        <div class="logo-container"></div>
        <h1 class="title">Título</h1>
        <form class="login-card"><input id="field" /></form>
      </div>
    </section>
    <section class="auth-right"><img alt="" /></section>
  `;
  return root;
};

// Mirrors the browser measurement the module does: two half-width plates, or a single one.
const mockPlates = (root, { artVisible = true, formLeft = 0 } = {}) => {
  const form = root.querySelector('.auth-left');
  const art = root.querySelector('.auth-right');
  const formWidth = 500;
  vi.spyOn(form, 'getBoundingClientRect').mockReturnValue({ left: formLeft, width: formWidth, height: 800 });
  vi.spyOn(art, 'getBoundingClientRect').mockReturnValue({
    left: formLeft + formWidth,
    width: artVisible ? formWidth : 0,
    height: artVisible ? 800 : 0,
  });
  Object.defineProperty(document.documentElement, 'clientWidth', { configurable: true, value: formWidth * 2 });
  return { form, art };
};

const cssColor = (hex) => {
  const probe = document.createElement('div');
  probe.style.backgroundColor = hex;
  return probe.style.backgroundColor;
};

beforeEach(() => {
  resetAuthPanelSwap();
});

afterEach(() => {
  vi.useRealTimers();
  resetAuthPanelSwap();
  delete document.documentElement.clientWidth;
});

describe('auth panel handoff', () => {
  it('matches the handoff to its own route and ignores other routes', () => {
    armAuthPanelSwap({ pathname: '/register', keyboard: true });

    expect(readAuthPanelSwap('/register')).toMatchObject({ keyboard: true });
    expect(readAuthPanelSwap('/register/')).toMatchObject({ keyboard: true });
    expect(readAuthPanelSwap('/login')).toBeNull();
  });

  it('drops a handoff the destination never reached in time', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-08T12:00:00Z'));
    armAuthPanelSwap({ pathname: '/login' });

    expect(readAuthPanelSwap('/login')).not.toBeNull();
    vi.setSystemTime(new Date('2026-10-08T12:00:01.700Z'));
    expect(readAuthPanelSwap('/login')).toBeNull();
  });

  it('changes the route on the press, wearing the destination surface', () => {
    const root = buildPlates();
    const { form } = mockPlates(root);
    const navigate = vi.fn();
    const surface = cssColor('#f8fafc');

    openAuthPanel({ root, targetPath: '/register', navigate });

    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/register');
    // Set while the plates still cover the viewport: the switch itself is never visible.
    expect(root.style.backgroundColor).toBe(surface);
    expect(form.style.backgroundColor).toBe(surface);
    expect(readAuthPanelSwap('/register')).not.toBeNull();
  });

  it('enters without a root, as the gateway does', () => {
    const navigate = vi.fn();

    openAuthPanel({ root: null, targetPath: '/login', keyboard: true, navigate });

    expect(navigate).toHaveBeenCalledWith('/login');
    expect(readAuthPanelSwap('/login')).toMatchObject({ keyboard: true });
  });
});

describe('resolveAuthPlateMotion', () => {
  const halfWidthPlates = { formWidth: 500, viewportWidth: 1000, artVisible: true };

  it('exchanges when both plates are on screen at half width', () => {
    expect(resolveAuthPlateMotion(halfWidthPlates)).toBe('exchange');
  });

  it('lands in place when a single plate owns the frame', () => {
    expect(resolveAuthPlateMotion({ ...halfWidthPlates, formWidth: 1000 })).toBe('in-place');
    expect(resolveAuthPlateMotion({ ...halfWidthPlates, artVisible: false })).toBe('in-place');
  });
});

describe('the arrival', () => {
  it('sweeps the art in from the half the page that left had, and leaves the form in place', () => {
    const arriving = buildPlates();
    document.body.appendChild(arriving);
    // Register: the form sits on the right, so the art starts on the left half.
    const { form, art } = mockPlates(arriving, { formLeft: 500 });
    const card = arriving.querySelector('.login-card');
    const field = arriving.querySelector('#field');

    const entry = playAuthPlateEntry(arriving, { reducedMotion: false, focusTarget: field });

    // The art starts where the page that left had it; the form is already in its own half.
    expect(form.style.transform).toBe('');
    expect(art.style.transform).toContain('500px');
    // The text is hazed out before the art clears it.
    expect(card.style.opacity).toBe('0');
    expect(arriving.classList.contains('auth--swapping')).toBe(true);

    // Focus lands once the art clears the form, before the haze has settled.
    entry.progress(0.9);
    expect(form.style.transform).toBe('');
    expect(art.style.transform).toBe('');
    expect(arriving.classList.contains('auth--swapping')).toBe(false);
    expect(document.activeElement).toBe(field);
    entry.progress(1);
    expect(card.style.opacity).toBe('');
    arriving.remove();
  });

  it('sweeps the art the other way on the page whose form sits on the left', () => {
    const arriving = buildPlates();
    mockPlates(arriving, { formLeft: 0 });

    const entry = playAuthPlateEntry(arriving, { reducedMotion: false });

    expect(arriving.querySelector('.auth-left').style.transform).toBe('');
    expect(arriving.querySelector('.auth-right').style.transform).toContain('-500px');
    entry.progress(1);
    expect(arriving.querySelector('.auth-left').style.transform).toBe('');
  });

  it('lands in place when a single plate owns the frame', () => {
    const arriving = buildPlates();
    const { form, art } = mockPlates(arriving, { artVisible: false });
    const card = arriving.querySelector('.login-card');

    const entry = playAuthPlateEntry(arriving, { reducedMotion: false });

    // Nothing travels, but the text still condenses in.
    expect(form.style.transform).toBe('');
    expect(art.style.transform).toBe('');
    expect(card.style.opacity).toBe('0');
    expect(arriving.classList.contains('auth--swapping')).toBe(false);
    entry.progress(1);
    expect(card.style.opacity).toBe('');
    expect(form.style.transform).toBe('');
  });

  it('does not move anything when motion is reduced', () => {
    const arriving = buildPlates();
    mockPlates(arriving, { formLeft: 500 });

    const entry = playAuthPlateEntry(arriving, { reducedMotion: true });

    expect(arriving.querySelector('.auth-left').style.transform).toBe('');
    entry.progress(1);
    expect(arriving.classList.contains('auth--swapping')).toBe(false);
  });

  it('survives a page without plates', () => {
    const entry = playAuthPlateEntry(document.createElement('div'), { reducedMotion: false });

    expect(entry.duration()).toBe(0);
  });
});

describe('first paint', () => {
  it('leaves page content visible and settles it', () => {
    const root = buildPlates();
    const card = root.querySelector('.login-card');

    const entrance = playAuthPageEntrance(root);
    expect(card.style.opacity).toBe('0');
    expect(card.style.visibility).toBe('');
    entrance.progress(1);
    expect(card.style.opacity).toBe('');
    expect(card.style.transform).toBe('');
  });
});
