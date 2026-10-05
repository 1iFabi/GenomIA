import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { Fingerprint } from 'lucide-react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Sidebar from './Sidebar';

vi.mock('../ChangePasswordModal/ChangePasswordModal.jsx', () => ({
  default: ({ isOpen }) => isOpen ? <div role="dialog" aria-label="Change password" /> : null,
}));
vi.mock('../DeleteAccountModal/DeleteAccountModal.jsx', () => ({
  default: ({ isOpen }) => isOpen ? <div role="dialog" aria-label="Delete account" /> : null,
}));

const items = [
  { label: 'Ancestría', href: '/dashboard/ancestria' },
  { label: 'Rasgos', href: '/dashboard/rasgos' },
  { label: 'Enfermedades', href: '/dashboard/enfermedades' },
  { label: 'Continentes', href: '/dashboard/continentes' },
  { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
  { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
];

let root;
let host;
let originalInnerWidth;
let originalActEnvironment;

beforeEach(() => {
  originalActEnvironment = globalThis.IS_REACT_ACT_ENVIRONMENT;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
});

const LocationMarker = () => <output data-testid="location">{useLocation().pathname}</output>;

const renderSidebar = async (iconOverrides, { user = {}, width = 390, onLogout, closeMenu = vi.fn() } = {}) => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  originalInnerWidth = window.innerWidth;
  window.innerWidth = width;

  await act(async () => {
    root.render(
      <MemoryRouter>
        <Sidebar
          items={items}
          user={user}
          isMobileMenuOpen
          setIsMobileMenuOpen={closeMenu}
          onLogout={onLogout}
          iconOverrides={iconOverrides}
        />
        <LocationMarker />
      </MemoryRouter>
    );
  });

  if (width > 1024) {
    await act(async () => host.querySelector('.sidebar').dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
  }
  await act(async () => host.querySelector('.sidebar__categories-toggle').click());
  return host;
};

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  host?.remove();
  host = null;
  if (originalInnerWidth !== undefined) window.innerWidth = originalInnerWidth;
  originalInnerWidth = undefined;
  if (originalActEnvironment === undefined) delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  else globalThis.IS_REACT_ACT_ENVIRONMENT = originalActEnvironment;
  originalActEnvironment = undefined;
  vi.clearAllMocks();
});

describe('Sidebar legacy upload retirement', () => {
  it.each([390, 1280])('does not expose a genetic-upload admin section at width %s', async (width) => {
    const sidebar = await renderSidebar(undefined, { user: { is_staff: true }, width });

    expect(sidebar.querySelector('.sidebar__admin-toggle')).toBeNull();
    expect(sidebar.textContent).not.toContain('Subir Archivo');
    expect(document.body.querySelector('.upload-modal-overlay')).toBeNull();
    expect(sidebar.querySelectorAll('.sidebar__categories-item')).toHaveLength(items.length);
  });

  it.each([390, 1280])('preserves profile actions, category navigation and logout at width %s', async (width) => {
    const onLogout = vi.fn();
    const closeMenu = vi.fn();
    const sidebar = await renderSidebar(undefined, { user: { is_staff: true, first_name: 'Reviewer' }, width, onLogout, closeMenu });
    await act(async () => sidebar.querySelector('.sidebar__profile-toggle').click());
    expect(sidebar.textContent).toContain('Hola Reviewer');
    const profileActions = sidebar.querySelectorAll('.sidebar__profile-button');
    expect([...profileActions].map((button) => button.textContent))
      .toEqual(['Cambiar contraseña', 'Eliminar cuenta']);
    await act(async () => profileActions[0].click());
    expect(document.body.querySelector('[role="dialog"][aria-label="Change password"]')).not.toBeNull();
    await act(async () => profileActions[1].click());
    expect(document.body.querySelector('[role="dialog"][aria-label="Delete account"]')).not.toBeNull();
    closeMenu.mockClear();
    await act(async () => sidebar.querySelector('.sidebar__categories-item').click());
    expect(sidebar.querySelector('[data-testid="location"]').textContent).toBe('/dashboard/ancestria');
    if (width <= 1024) expect(closeMenu).toHaveBeenCalledWith(false);
    await act(async () => sidebar.querySelector('.sidebar__brand').click());
    expect(sidebar.querySelector('[data-testid="location"]').textContent).toBe('/dashboard');
    await act(async () => sidebar.querySelector('.sidebar__home').click());
    expect(sidebar.querySelector('[data-testid="location"]').textContent).toBe('/');
    await act(async () => sidebar.querySelector('.sidebar__logout').click());
    expect(onLogout).toHaveBeenCalledOnce();
  });
});

describe('Sidebar icon overrides', () => {
  it('keeps the existing category icon defaults when no overrides are supplied', async () => {
    const sidebar = await renderSidebar();
    const categoryButtons = sidebar.querySelectorAll('.sidebar__categories-item');
    const expectedIcons = ['dna', 'activity', 'heart', 'globe', 'pill', 'test-tube'];

    expect(categoryButtons).toHaveLength(6);
    expect([...categoryButtons].map((button) => (
      [...button.querySelector('svg').classList].find((className) => className.startsWith('lucide-'))
    ))).toEqual(expectedIcons.map((name) => `lucide-${name}`));
  });

  it('uses supplied Lucide icons and falls back for unspecified icons', async () => {
    const sidebar = await renderSidebar({ categoryItems: [Fingerprint] });
    const categoryButtons = sidebar.querySelectorAll('.sidebar__categories-item');

    expect(categoryButtons).toHaveLength(items.length);
    expect(categoryButtons[0].querySelector('svg.lucide-fingerprint')).not.toBeNull();
    expect(categoryButtons[1].querySelector('svg.lucide-activity')).not.toBeNull();
  });
});
