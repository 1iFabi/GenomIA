import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PostloginUser from './PostloginUser';

vi.mock('./Dashboard', () => ({ default: () => <div data-testid="user-home" /> }));
vi.mock('../Ancestria/Ancestria', () => ({ default: () => <div data-testid="ancestria" /> }));
vi.mock('../Rasgos/Rasgos', () => ({ default: () => <div data-testid="rasgos" /> }));
vi.mock('../Enfermedades/Enfermedades', () => ({ default: () => <div data-testid="enfermedades" /> }));
vi.mock('../Farmacogenetica/Farmacogenetica', () => ({ default: () => <div data-testid="farmacogenetica" /> }));
vi.mock('../Biomarcadores/Biomarcadores', () => ({ default: () => <div data-testid="biomarcadores" /> }));
vi.mock('../Biometrics/Biometrics', () => ({ default: () => <div data-testid="biometricas" /> }));

let container;
let root;
const renderRoute = async (path) => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard/*" element={<PostloginUser user={{ id: 1 }} />} />
      </Routes>
    </MemoryRouter>
  ));
  return container;
};
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container?.remove();
  container = null;
});

describe('user result routes', () => {
  it.each(['biomarcadores', 'biometricas'])('does not register the retired %s route', async (path) => {
    const view = await renderRoute(`/dashboard/${path}`);
    expect(view.querySelector(`[data-testid="${path}"]`)).toBeNull();
    expect(view.childElementCount).toBe(0);
  });

  it.each([
    ['', 'user-home'], ['ancestria', 'ancestria'], ['rasgos', 'rasgos'],
    ['enfermedades', 'enfermedades'], ['farmacogenetica', 'farmacogenetica'],
  ])('preserves the retained /dashboard/%s route', async (path, marker) => {
    const view = await renderRoute(`/dashboard/${path}`);
    expect(view.querySelector(`[data-testid="${marker}"]`)).not.toBeNull();
  });
});
