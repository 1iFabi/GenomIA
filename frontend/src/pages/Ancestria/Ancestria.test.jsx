import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cwd } from 'node:process';
import React, { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ChevronDown as ChevronDownIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
  ChevronUp as ChevronUpIcon,
  ChevronsLeft as ChevronsLeftIcon,
  FlaskConical as PharmacogeneticsIcon,
  Map as AncestryIcon,
  Menu as MenuIcon,
  Stethoscope as DiseaseIcon,
  UserRound as TraitsIcon,
  X as CloseIcon,
} from '@animateicons/react/lucide';
import { Expand as ExpandIcon, Shrink as ShrinkIcon } from 'lucide-react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { AuthProvider } from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/ProtectedRoute';
import Ancestria from './Ancestria';

const apiImplementation = vi.hoisted(() => ({ request: null }));
vi.mock('../../config/api', async (importOriginal) => {
  const actual = await importOriginal();
  apiImplementation.request = actual.apiRequest;
  return {
    ...actual,
    apiRequest: vi.fn(actual.apiRequest),
    clearToken: vi.fn(),
  };
});

vi.mock('../../components/Sidebar/Sidebar', () => ({
  default: ({ items, iconOverrides, user, onLogout }) => (
    <nav aria-label="Dashboard navigation" data-has-icon-overrides={Boolean(iconOverrides)}>
      <span data-testid="shared-user">{user?.name}</span>
      {items.map((item) => <a key={item.href} href={item.href}>{item.label}</a>)}
      <button type="button" onClick={onLogout}>Cerrar sesión</button>
      {iconOverrides?.categoryItems?.map((Icon, index) => (
        <Icon key={index} data-testid={`ancestria-sidebar-icon-${index}`} aria-hidden="true" />
      ))}
    </nav>
  ),
}));

vi.mock('../../components/SectionHeader/SectionHeader', () => ({
  default: ({ title }) => <header>{title}</header>,
}));

const createWorldTopology = () => {
  const countries = [
    [152, 'Chile', -71, -30],
    [246, 'Finland', 25, 64],
    [724, 'Spain', -4, 40],
    ['032', 'Argentina', -64, -34],
    [604, 'Peru', -75, -9],
    [380, 'Italy', 12, 42],
    [484, 'Mexico', 15, 23],
  ];
  const arcs = [];
  const geometries = countries.map(([id, name, longitude, latitude]) => {
    const ring = [
      [longitude - 2, latitude - 2],
      [longitude + 2, latitude - 2],
      [longitude + 2, latitude + 2],
      [longitude - 2, latitude + 2],
      [longitude - 2, latitude - 2],
    ];
    const index = arcs.length;
    arcs.push(ring.map((point, pointIndex) => (
      pointIndex === 0
        ? point
        : [point[0] - ring[pointIndex - 1][0], point[1] - ring[pointIndex - 1][1]]
    )));
    return { type: 'Polygon', id, properties: { name }, arcs: [[index]] };
  });
  return {
    type: 'Topology',
    arcs,
    objects: { countries: { type: 'GeometryCollection', geometries } },
  };
};

const createWorldTopologyResponse = () => {
  const bytes = new TextEncoder().encode(JSON.stringify(createWorldTopology()));
  let isRead = false;
  return {
    ok: true,
    headers: { get: () => null },
    body: {
      getReader: () => ({
        read: async () => {
          if (isRead) return { done: true };
          isRead = true;
          return { done: false, value: bytes };
        },
        cancel: async () => {},
      }),
      cancel: async () => {},
    },
  };
};

const ancestryStyles = readFileSync(
  resolve(cwd(), 'src/pages/Ancestria/Ancestria.css'),
  'utf8'
);

const getFirstCssDeclaration = (source, selector, property) => {
  const rule = source.match(new RegExp(`${selector}\\s*\\{([^}]*)\\}`))?.[1] ?? '';
  return rule
    .split(';')
    .map((declaration) => declaration.trim())
    .filter(Boolean)
    .map((declaration) => declaration.match(/^([\w-]+)\s*:\s*(.+)$/))
    .find((match) => match?.[1] === property)?.[2].trim();
};

const getLastCssDeclaration = (source, selector, property) => {
  const matchingRules = [...source.matchAll(new RegExp(`${selector}\\s*\\{([^}]*)\\}`, 'g'))];
  const declarations = matchingRules.flatMap(([, body]) => body
    .split(';')
    .map((declaration) => declaration.trim())
    .filter(Boolean)
    .map((declaration) => declaration.match(/^([\w-]+)\s*:\s*(.+)$/))
    .filter((match) => match?.[1] === property)
    .map((match) => match[2].trim()));
  return declarations.at(-1);
};

const parseCssColor = (value) => {
  if (value?.startsWith('#')) {
    const hex = value.slice(1);
    const expanded = hex.length === 3 ? [...hex].map((digit) => digit + digit).join('') : hex;
    if (expanded.length === 6) {
      return [...[0, 2, 4].map((offset) => Number.parseInt(expanded.slice(offset, offset + 2), 16)), 1];
    }
  }
  const start = value?.indexOf('(') ?? -1;
  const end = value?.lastIndexOf(')') ?? -1;
  if (start < 0 || end <= start) return null;
  const channels = value.slice(start + 1, end).split(',').map((channel) => Number.parseFloat(channel.trim()));
  return channels.length >= 3 && channels.slice(0, 3).every(Number.isFinite)
    ? [...channels.slice(0, 3), channels[3] ?? 1]
    : null;
};

const contrastRatio = (foreground, background) => {
  const luminance = (color) => color.slice(0, 3)
    .map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    })
    .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
};

const fixture = JSON.parse(readFileSync(
  resolve(cwd(), '../backend/sequoh/genoma/fixtures/synthetic_genomics_v2.json'), 'utf8'
));
const { modules: fixtureModules, ...fixtureDisclosure } = fixture;
const createService = (id = 'latest', purchasedAt = '2026-09-24T12:00:00Z', version = '2') => ({
  service_request_id: id, purchased_at: purchasedAt, release_version: version,
  synthetic: true, non_clinical: true, disclaimer: fixtureDisclosure.disclaimer,
});
const createResults = (service = createService()) => ({
  ...service,
  results: fixtureModules.map((module) => ({
    module: module.module, result_type: 'synthetic_placeholder',
    value_code: 'SYNTHETIC_NOT_EVALUATED', payload: structuredClone({ ...fixtureDisclosure, ...module }),
  })),
});
const reply = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
});
const deferred = () => {
  let resolve;
  const promise = new Promise((res) => { resolve = res; });
  return { promise, resolve };
};
const getResultStatus = () => container.querySelector('.ancestria-results-status');
const getGlobalSection = () => container.querySelector('[aria-labelledby="ancestria-global-title"]');
const getLocalSection = () => container.querySelector('[aria-labelledby="ancestria-local-title"]');
const expectNeutralCopy = () => {
  const copy = container.querySelector('main');
  const accessibleCopy = [...copy.querySelectorAll('[aria-label], [aria-description], [aria-valuetext], [title], [alt]')]
    .flatMap((node) => ['aria-label', 'aria-description', 'aria-valuetext', 'title', 'alt']
      .map((attribute) => node.getAttribute(attribute) || '')).join(' ');
  expect(`${copy.textContent} ${accessibleCopy}`).not.toMatch(
    /demo|demostraci[oó]n|sint[eé]tic[oa]s?|synthetic|no[\s_-]+evaluad[oa]s?|not[\s_-]+evaluated|no cl[ií]nic[oa]s?|non[\s_-]+clinical|sin revisi[oó]n cl[ií]nica|arbitrari[oa]s?/i
  );
};

let root;
let container;
let originalInnerWidth;
let originalMatchMedia;
let fullscreenApiDescriptors;

const installMockFullscreenApi = () => {
  fullscreenApiDescriptors = {
    requestFullscreen: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'requestFullscreen'),
    exitFullscreen: Object.getOwnPropertyDescriptor(document, 'exitFullscreen'),
    fullscreenElement: Object.getOwnPropertyDescriptor(document, 'fullscreenElement'),
  };
  let fullscreenElement = null;
  const requestFullscreen = vi.fn(async function requestFullscreen() {
    fullscreenElement = this;
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  const exitFullscreen = vi.fn(async () => {
    fullscreenElement = null;
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
    configurable: true,
    value: requestFullscreen,
  });
  Object.defineProperty(document, 'exitFullscreen', {
    configurable: true,
    value: exitFullscreen,
  });
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    get: () => fullscreenElement,
  });

  return {
    requestFullscreen,
    exitFullscreen,
    setFullscreenElement: (element) => { fullscreenElement = element; },
    dispatchFullscreenChange: () => document.dispatchEvent(new Event('fullscreenchange')),
  };
};

const restoreFullscreenApi = () => {
  if (!fullscreenApiDescriptors) return;
  const restore = (target, property, descriptor) => {
    if (descriptor) Object.defineProperty(target, property, descriptor);
    else delete target[property];
  };
  restore(HTMLElement.prototype, 'requestFullscreen', fullscreenApiDescriptors.requestFullscreen);
  restore(document, 'exitFullscreen', fullscreenApiDescriptors.exitFullscreen);
  restore(document, 'fullscreenElement', fullscreenApiDescriptors.fullscreenElement);
  fullscreenApiDescriptors = null;
};

const getFullscreenToggle = () => [...container.querySelectorAll('button')]
  .find((button) => [...button.classList].some((className) => /fullscreen|pantalla-completa/i.test(className)));

const animateIconReferences = {
  menu: MenuIcon,
  x: CloseIcon,
  'chevron-up': ChevronUpIcon,
  'chevron-down': ChevronDownIcon,
  'chevron-left': ChevronLeftIcon,
  'chevrons-left': ChevronsLeftIcon,
  'chevron-right': ChevronRightIcon,
};

const getIconGeometry = (svg) => [...svg.querySelectorAll('path, circle, rect, line, polyline, polygon, ellipse')]
  .map((shape) => ({
    tag: shape.tagName.toLowerCase(),
    attributes: [...shape.attributes]
      .filter(({ name }) => !['style', 'pathlength', 'stroke-dasharray', 'stroke-dashoffset', 'opacity']
        .includes(name.toLowerCase()))
      .map(({ name, value }) => [name, value])
      .sort(([left], [right]) => left.localeCompare(right)),
  }));

const cachedReferenceIconGeometry = new WeakMap();

const getReferenceIconGeometry = (Icon, size, iconProps = { duration: 0.6 }) => {
  let geometryBySize = cachedReferenceIconGeometry.get(Icon);
  if (!geometryBySize) {
    geometryBySize = new Map();
    cachedReferenceIconGeometry.set(Icon, geometryBySize);
  }
  if (!geometryBySize.has(size)) {
    const reference = document.createElement('div');
    const logError = console.error;
    const warningSpy = vi.spyOn(console, 'error').mockImplementation((...args) => {
      if (!String(args[0]).includes('useLayoutEffect does nothing on the server')) {
        logError(...args);
      }
    });
    try {
      reference.innerHTML = renderToStaticMarkup(createElement(Icon, { size, ...iconProps }));
    } finally {
      warningSpy.mockRestore();
    }
    geometryBySize.set(size, getIconGeometry(reference.querySelector('svg')));
  }
  return geometryBySize.get(size);
};

const expectAnimateIconDecorativeIcon = (control, iconName) => {
  const svg = control.querySelector('svg');
  expect(svg).not.toBeNull();
  expect(svg?.parentElement).not.toBe(control);
  expect(svg?.parentElement?.getAttribute('aria-hidden')).toBe('true');
  expect(svg?.getAttribute('stroke')).toBe('currentColor');
  const ExpectedIcon = animateIconReferences[iconName];
  expect(ExpectedIcon, `expected a verified AnimateIcons export for ${iconName}`).toBeDefined();
  if (ExpectedIcon && svg) {
    expect(getIconGeometry(svg)).toEqual(getReferenceIconGeometry(ExpectedIcon, Number(svg.getAttribute('width'))));
  }
  return svg;
};

const expectLucideDecorativeIcon = (control, Icon) => {
  const svg = control.querySelector('svg');
  expect(svg).not.toBeNull();
  expect(svg?.parentElement).toBe(control);
  expect(svg?.getAttribute('aria-hidden')).toBe('true');
  expect(svg?.getAttribute('stroke')).toBe('currentColor');
  expect(svg?.hasAttribute('duration')).toBe(false);
  if (svg) {
    expect(getIconGeometry(svg)).toEqual(
      getReferenceIconGeometry(Icon, Number(svg.getAttribute('width')), {})
    );
  }
  return svg;
};

const getFullscreenClass = (element) => [...element.classList]
  .find((className) => /fullscreen|pantalla-completa/i.test(className));

const waitFor = async (predicate) => {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });
  }
  throw new Error('Timed out waiting for the Ancestria page to update.');
};

const mockApi = ({
  services = [createService()], results = createResults(), listStatus = 200,
  resultStatus = 200, profile = reply({ user: { id: 1 } }),
} = {}) => {
  fetch.mockImplementation(async (endpoint) => {
    if (endpoint === API_ENDPOINTS.ME) return profile;
    if (endpoint === API_ENDPOINTS.GENOMICS_SERVICES) {
      return services instanceof Promise ? services : reply({ services }, listStatus);
    }
    if (String(endpoint).startsWith(API_ENDPOINTS.GENOMICS_SERVICES)) {
      return results instanceof Promise ? results : reply(results, resultStatus);
    }
    return createWorldTopologyResponse();
  });
};

const dispatchPointerEvent = async (target, type, init = {}) => {
  const event = new MouseEvent(type, {
    bubbles: true,
    clientX: init.clientX ?? 0,
    clientY: init.clientY ?? 0,
  });
  Object.defineProperty(event, 'pointerId', { value: init.pointerId ?? 1 });
  await act(async () => target.dispatchEvent(event));
};

const rotateGlobeAndConsumeDragClick = async (map) => {
  await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
  await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
  await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
  await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
};

const openDrawer = async () => {
  const toggle = container.querySelector('[aria-controls="ancestria-insight-panel"]');
  expect(toggle).not.toBeNull();
  await act(async () => toggle.click());
  return toggle;
};

const LocationMarker = () => <output aria-label="Current route">{useLocation().pathname}</output>;

const renderPage = async ({ protectedRoute = false } = {}) => {
  if (!root) {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  }

  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/dashboard/ancestria']}>
        <AuthProvider>
          {protectedRoute ? (
            <React.StrictMode><ProtectedRoute><Ancestria /></ProtectedRoute></React.StrictMode>
          ) : <Ancestria />}
        </AuthProvider>
        <LocationMarker />
      </MemoryRouter>
    );
  });
  await waitFor(() => fetch.mock.calls.some(([endpoint]) => endpoint === API_ENDPOINTS.GENOMICS_SERVICES));
};

beforeEach(() => {
  fullscreenApiDescriptors = null;
  originalInnerWidth = window.innerWidth;
  originalMatchMedia = window.matchMedia;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.requestAnimationFrame = (callback) => window.setTimeout(
    () => callback(performance.now()),
    1000 / 60
  );
  window.cancelAnimationFrame = (frame) => window.clearTimeout(frame);
  vi.mocked(clearToken).mockReset();
  vi.mocked(apiRequest).mockReset();
  vi.mocked(apiRequest).mockImplementation(apiImplementation.request);
  vi.stubGlobal('fetch', vi.fn());
  mockApi();
});

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
  document.body.querySelectorAll('.country-insight-popover, .country-insight-popover__backdrop').forEach((node) => node.remove());
  document.head.querySelectorAll('style[data-country-popover-test]').forEach((node) => node.remove());
  window.innerWidth = originalInnerWidth;
  window.matchMedia = originalMatchMedia;
  restoreFullscreenApi();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('Ancestria insight rail', () => {
  it('clears the shared session once and navigates home without a direct logout POST', async () => {
    await renderPage();
    await act(async () => [...container.querySelectorAll('nav button')]
      .find((button) => button.textContent === 'Cerrar sesión').click());
    expect(clearToken).toHaveBeenCalledExactlyOnceWith();
    expect(apiRequest.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(0);
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/');
  });

  it('waits for shared best-effort logout to complete before navigating home', async () => {
    const logout = deferred();
    clearToken.mockReturnValueOnce(logout.promise);
    await renderPage();
    await act(async () => [...container.querySelectorAll('nav button')]
      .find((button) => button.textContent === 'Cerrar sesión').click());
    expect(clearToken).toHaveBeenCalledExactlyOnceWith();
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/dashboard/ancestria');
    await act(async () => logout.resolve());
    expect(container.querySelector('[aria-label="Current route"]').textContent).toBe('/');
    expect(clearToken).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls.filter(([url]) => url === API_ENDPOINTS.LOGOUT)).toHaveLength(0);
  });

  it('reuses the StrictMode guard profile and retains it after the result page remounts', async () => {
    mockApi({ profile: reply({ user: { name: 'Ada', service_status: 'COMPLETED' } }) });
    await renderPage({ protectedRoute: true });
    expect(container.querySelector('[data-testid="shared-user"]').textContent).toBe('Ada');
    await renderPage();
    expect(container.querySelector('[data-testid="shared-user"]').textContent).toBe('Ada');
    expect(fetch.mock.calls.filter(([url]) => url === API_ENDPOINTS.ME)).toHaveLength(1);
  });

  it('resolves the same ancestry fixture from the future genoma package', () => {
    const fixturePath = resolve(cwd(), '../backend/sequoh/genoma/fixtures/synthetic_genomics_v2.json');
    // Keep the current fixture above importable; fail explicitly before reading the future path.
    expect(existsSync(fixturePath), 'expected the packaged ancestry fixture under genoma').toBe(true);
    expect(JSON.parse(readFileSync(fixturePath, 'utf8'))).toEqual(fixture);
  });

  it('loads the latest purchase through normalized HTTP and localizes both displays in API order', async () => {
    const latest = createService('newest/a b', '2026-09-24T12:00:00Z', '1');
    const results = createResults(latest);
    const rawResults = structuredClone(results);
    mockApi({
      services: [createService('older', '2026-09-23T12:00:00Z', '99'), latest],
      results,
    });
    await renderPage();
    await openDrawer();

    expect(getGlobalSection()?.querySelector('h3').textContent).toBe('Ancestría global');
    expect([...getGlobalSection().querySelectorAll('li')].map((row) => row.textContent))
      .toEqual(['Grupo A: 60%', 'Grupo B: 40%']);
    expect(getLocalSection()?.querySelector('h3').textContent).toBe('Ancestría local');
    expect(getLocalSection().textContent).toContain('Eje A');
    expect(getLocalSection().textContent).toContain('Extensión: 100 unidades');
    expect([...getLocalSection().querySelectorAll('li')].map((row) => row.textContent)).toEqual([
      'Grupo A: inicio 0 · longitud 60 unidades',
      'Grupo B: inicio 60 · longitud 40 unidades',
    ]);
    expect(getLocalSection().textContent).not.toContain('%');
    expectNeutralCopy();
    expect(results).toEqual(rawResults);
    expect(getResultStatus().getAttribute('aria-label')).toBe('Estado de los resultados');
    expect(getResultStatus().querySelector('button').getAttribute('aria-label')).toBe('Reintentar carga de resultados');
    const normalizedCalls = fetch.mock.calls.filter(([url]) => /\/(genoma|genomics)\//.test(String(url)));
    expect(normalizedCalls).toEqual([
      ['/api/genoma/v1/services/', { method: 'GET', credentials: 'include', headers: {} }],
      [`/api/genoma/v1/services/${encodeURIComponent(latest.service_request_id)}/results/`,
        { method: 'GET', credentials: 'include', headers: {} }],
    ]);
    expect(fetch.mock.calls.some(([url]) => /\/api\/genetics\//.test(String(url)))).toBe(false);
    expect(container.textContent).not.toMatch(/Demo index|Demo trait|Demo interaction/);
  });
  it('uses the effective charcoal map-card surface with a subtle light border', () => {
    const selector = '\\.ancestria-page__chart-card';

    expect(getLastCssDeclaration(ancestryStyles, selector, 'background')).toBe('#4F4F4F');
    expect(getLastCssDeclaration(ancestryStyles, selector, 'border'))
      .toBe('1px solid rgba(255, 255, 255, 0.14)');
    expect(getLastCssDeclaration(ancestryStyles, selector, 'box-shadow'))
      .toBe('0 0.5rem 1.5rem rgba(15, 35, 65, 0.08)');
  });

  it('uses the current globe palette with a bright white graticule', async () => {
    await renderPage();

    const sphere = container.querySelector('[data-globe-sphere="true"]');
    const graticule = container.querySelector('[data-globe-graticule="true"]');

    expect(sphere?.getAttribute('fill')).toBe('#F0EBD8');
    expect(graticule?.getAttribute('stroke')).toBe('#FFFFFF');
    expect(Number(graticule?.getAttribute('opacity'))).toBeGreaterThan(0.31);
    expect(container.querySelector('[data-geography-id="152"]')?.getAttribute('fill'))
      .toBe('#3E5C76');
    expect(container.querySelector('[data-geography-id="246"]')?.getAttribute('fill'))
      .toBe('#3E5C76');
    expect(container.querySelector('[data-geography-id="380"]')?.getAttribute('fill'))
      .toBe('#3E5C76');
  });

  it('replaces the compass with the rotating coin at the top-right map mark', async () => {
    await renderPage();

    const mapCard = container.querySelector('.ancestria-page__chart-card');
    const mark = mapCard.querySelector('.ancestria-map-mark');
    const coin = mark?.querySelector('.coin-scene .coin');

    expect(mapCard.querySelector('.ancestria-map-compass')).toBeNull();
    expect(coin).not.toBeNull();
    expect(coin?.classList.contains('coin--flat') || coin?.classList.contains('coin--3d')).toBe(true);
    expect(coin?.style.animationDuration).not.toBe('');
    expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'position')).toBe('absolute');
    const markRight = getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'right');
    expect(['rem', 'px'].some((unit) => markRight?.endsWith(unit))).toBe(true);
  });

  it('shows a white map logo while closed and a black logo alongside the open panel title', async () => {
    await renderPage();

    const mapCard = container.querySelector('.ancestria-page__chart-card');
    const mapLogo = mapCard.querySelector('.ancestria-map-mark img');
    expect.soft(mapLogo).not.toBeNull();
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'filter'))
      .toMatch(/brightness\(0\).*invert\(1\)/);
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'top')).toBe('1rem');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'right')).toBe('1rem');

    const panel = container.querySelector('#ancestria-insight-panel');
    const closedTitle = panel.querySelector('.ancestria-insight-rail__title');
    expect.soft(closedTitle.querySelector('img')).toBeNull();

    await openDrawer();

    const openTitle = panel.querySelector('.ancestria-insight-rail__title');
    const panelLogo = openTitle.querySelector('img');
    expect.soft(openTitle.textContent.trim()).toBe('Resultados');
    expect.soft(panelLogo).not.toBeNull();
    expect.soft(mapCard.querySelector('.ancestria-map-mark img')).toBeNull();
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-insight-rail__title img', 'filter') ?? '')
      .toMatch(/brightness\(0\)(?!.*invert)/);
  });

  it('keeps the fullscreen control framed while leaving the drawer hit target unframed and keyboard-visible', () => {
    const controls = [
      { className: 'ancestria-drawer-toggle', framed: false },
      { className: 'ancestria-fullscreen-toggle', framed: true },
    ];
    for (const { className, framed } of controls) {
      const selector = `\\.${className}`;
      const foreground = parseCssColor(getLastCssDeclaration(ancestryStyles, selector, 'color'));
      const border = getLastCssDeclaration(ancestryStyles, selector, 'border');
      const borderColor = parseCssColor(
        border?.match(/(?:#[\da-f]{3,8}|rgba?\([^)]*\))/i)?.[0]
      );
      const keylineShadow = getLastCssDeclaration(ancestryStyles, selector, 'box-shadow');
      const keylineColor = parseCssColor(
        keylineShadow?.match(/(?:rgba?\([^)]*\)|#[\da-f]{3,8})/i)?.[0]
      );

      expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'width'), `${className} width`)
        .toBe('48px');
      expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'height'), `${className} height`)
        .toBe('48px');
      expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'box-sizing')).toBe('border-box');
      expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'background'), `${className} background`)
        .toBe('transparent');
      expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'background-color'))
        .toBeUndefined();
      expect.soft(foreground, `${className} icon color`).toEqual([255, 255, 255, 1]);
      if (framed) {
        expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'border-radius')).toBe('50%');
        expect.soft(border).toBe('1px solid #ffffff');
        expect.soft(borderColor, `${className} border color`).toEqual([255, 255, 255, 1]);
        expect.soft(keylineShadow, `${className} should retain its thin dark outer keyline`)
          .toMatch(/^0 0 0 1px /);
        expect.soft(keylineColor, `${className} keyline color`).not.toBeNull();
        if (keylineColor && borderColor) {
          expect.soft(contrastRatio(keylineColor, parseCssColor('#FFFFFF')),
            `${className} dark keyline contrast on the light sidebar`).toBeGreaterThanOrEqual(3);
          expect.soft(contrastRatio(borderColor, parseCssColor('#4F4F4F')),
            `${className} white border contrast over the map`).toBeGreaterThanOrEqual(3);
        }
      } else {
        expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'border')).toBe('0');
        expect.soft(getLastCssDeclaration(ancestryStyles, selector, 'border-radius')).toBe('0');
        expect.soft(keylineShadow, `${className} must not draw a circular keyline`).toBe('none');
      }
      expect.soft(getLastCssDeclaration(ancestryStyles, `${selector} svg`, 'filter'),
        `${className} icon should have a small dark drop-shadow`)
        .toMatch(/drop-shadow\(0 1px 1px rgba\(15, 35, 65, 0\.9\)\)/);

      for (const state of ['hover', 'active']) {
        const stateSelector = `${selector}:${state}`;
        expect.soft(getLastCssDeclaration(ancestryStyles, stateSelector, 'background'),
          `${className} ${state} must stay unfilled`).toBeUndefined();
        expect.soft(getLastCssDeclaration(ancestryStyles, stateSelector, 'background-color'),
          `${className} ${state} must stay unfilled`).toBeUndefined();
        expect.soft(getLastCssDeclaration(ancestryStyles, stateSelector, 'box-shadow'),
          `${className} ${state} must not add a filled-state shadow`).toBeUndefined();
      }

      const focusRule = ancestryStyles.split(`.${className}:focus-visible`)[1]?.split('}')[0] || '';
      expect.soft(focusRule, `${className} must retain a visible focus-visible state`).not.toBe('');
      expect.soft(
        ['outline:', 'box-shadow:', 'filter:'].some((property) => focusRule.includes(property))
          && !focusRule.includes('outline: none')
          && !focusRule.includes('outline: 0'),
        `${className} focus-visible styling must remain visible`
      ).toBe(true);
      const focusOutline = parseCssColor(
        focusRule.match(/outline:\s*[^;]+/)?.[0]?.match(/(?:#[\da-f]{3,8}|rgba?\([^)]*\))/i)?.[0]
      );
      const focusRing = parseCssColor(
        focusRule.match(/box-shadow:\s*([^;]+)/)?.[1]
          ?.match(/(?:^|,)\s*0\s+0\s+0\s+[\d.]+px\s+(rgba?\([^)]*\)|#[\da-f]{3,8})/i)?.[1]
      );
      expect.soft(focusOutline, `${className} focus needs a white outline over the map`)
        .toEqual([255, 255, 255, 1]);
      expect.soft(focusRing, `${className} focus needs a dark outer ring on the sidebar`).not.toBeNull();
      if (focusOutline && focusRing) {
        expect.soft(contrastRatio(focusOutline, parseCssColor('#4F4F4F')),
          `${className} focus outline contrast on the map`).toBeGreaterThanOrEqual(3);
        expect.soft(contrastRatio(focusRing, parseCssColor('#FFFFFF')),
          `${className} focus ring contrast on the sidebar`).toBeGreaterThanOrEqual(3);
      }
    }

    const drawerSelector = '\\.ancestria-drawer-toggle';
    const mobileOpenSelector = '\\.ancestria-page__chart-card--drawer-open \\.ancestria-drawer-toggle';
    for (const property of ['width', 'height', 'border', 'border-bottom', 'border-radius']) {
      expect.soft(getLastCssDeclaration(ancestryStyles, mobileOpenSelector, property),
        `mobile open state must not override ${property}`).toBeUndefined();
    }

    expect.soft(getLastCssDeclaration(ancestryStyles, drawerSelector, 'background-color'),
      'reduced-transparency mode must keep the drawer toggle transparent').toBeUndefined();
    expect.soft(getFirstCssDeclaration(ancestryStyles, drawerSelector, 'top')).toBe('50%');
    expect.soft(getFirstCssDeclaration(ancestryStyles, drawerSelector, 'right')).toBe('0.25rem');
    expect.soft(getFirstCssDeclaration(ancestryStyles, mobileOpenSelector, 'right')).toBe('min(22rem, 86%)');

    const fullscreenSelector = '\\.ancestria-fullscreen-toggle';
    expect.soft(getLastCssDeclaration(ancestryStyles, fullscreenSelector, 'position')).toBe('absolute');
    expect.soft(getLastCssDeclaration(ancestryStyles, fullscreenSelector, 'right')).toBe('1rem');
    expect.soft(getLastCssDeclaration(ancestryStyles, fullscreenSelector, 'bottom')).toBe('1rem');

    const drawerFocusRule = ancestryStyles.split('.ancestria-drawer-toggle:focus-visible')[1]?.split('}')[0] || '';
    expect.soft(drawerFocusRule, 'drawer toggle must retain a visible focus-visible state').not.toBe('');
    expect.soft(
      ['outline:', 'box-shadow:', 'filter:'].some((property) => drawerFocusRule.includes(property))
        && !drawerFocusRule.includes('outline: none')
        && !drawerFocusRule.includes('outline: 0'),
      'drawer toggle focus-visible styling must remain visible'
    ).toBe(true);

    const focusOutline = parseCssColor(
      drawerFocusRule.match(/outline:\s*[^;]+/)?.[0]?.match(/(?:#[\da-f]{3,8}|rgba?\([^)]*\))/i)?.[0]
    );
    const outerRing = parseCssColor(
      drawerFocusRule.match(/box-shadow:\s*([^;]+)/)?.[1]
        ?.match(/(?:^|,)\s*0\s+0\s+0\s+[\d.]+px\s+(rgba?\([^)]*\)|#[\da-f]{3,8})/i)?.[1]
    );
    expect.soft(focusOutline, 'drawer focus needs a light outline against the dark map').not.toBeNull();
    expect.soft(outerRing, 'drawer focus needs a dark outer ring against the light sidebar').not.toBeNull();
    if (focusOutline && outerRing) {
      expect.soft(contrastRatio(focusOutline, parseCssColor('#4F4F4F')),
        'drawer focus outline contrast on the dark map').toBeGreaterThanOrEqual(3);
      expect.soft(contrastRatio(outerRing, parseCssColor('#FFFFFF')),
        'drawer focus outer-ring contrast on the light sidebar').toBeGreaterThanOrEqual(3);
    }

    const burgerControls = [
      { className: 'ancestria-dashboard__burger', surface: parseCssColor('#F3F7FF') },
    ];
    for (const { className, surface } of burgerControls) {
      const selector = `.${className}`;
      const background = parseCssColor(getLastCssDeclaration(ancestryStyles, selector, 'background'));
      const foreground = parseCssColor(getLastCssDeclaration(ancestryStyles, selector, 'color'));
      expect.soft(background, `${className} needs a translucent solid surface`).not.toBeNull();
      if (background) {
        expect.soft(background[3], `${className} surface should remain translucent`).toBeLessThan(1);
      }
      expect.soft(foreground, `${className} needs a parseable high-contrast foreground`).not.toBeNull();

      if (background && foreground) {
        const compositedSurface = background.slice(0, 3).map((channel, index) => (
          channel * background[3] + surface[index] * (1 - background[3])
        ));
        expect.soft(contrastRatio(foreground, compositedSurface), `${className} contrast`)
          .toBeGreaterThanOrEqual(4.5);
      }

      const focusRule = ancestryStyles.split(`.${className}:focus-visible`)[1]?.split('}')[0] || '';
      expect.soft(focusRule, `${className} must retain a visible focus-visible state`).not.toBe('');
      expect.soft(
        ['outline:', 'box-shadow:', 'filter:'].some((property) => focusRule.includes(property))
          && !focusRule.includes('outline: none')
          && !focusRule.includes('outline: 0'),
        `${className} focus-visible styling must remain visible`
      ).toBe(true);
    }
  });

  it('starts with a full-width map and the evidence drawer collapsed', async () => {
    await renderPage();

    const map = container.querySelector('.ancestria-page__chart-card');
    const toggle = container.querySelector('[aria-controls="ancestria-insight-panel"]');
    expect(map).not.toBeNull();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.getAttribute('aria-label')).toBe('Abrir panel de ancestría');
    expect(container.querySelector('#ancestria-insight-panel').getAttribute('aria-hidden')).toBe('true');
  });

  it('preserves the Ancestría title with neutral result and reference-map copy', async () => {
    await renderPage();

    expect(container.querySelector('.ancestria-page__title-main').textContent).toBe('ANCESTRÍA');
    expect(container.querySelector('.ancestria-page__title-supporting').textContent.trim())
      .toBe('Explora tus resultados y un mapa de referencia geográfica.');
    expectNeutralCopy();
  });

  it('preserves globe rotation while dismissing only the drawer on a map-background click', async () => {
    await renderPage();
    const map = container.querySelector('[data-projection="geoOrthographic"]');
    const drawerToggle = await openDrawer();
    await rotateGlobeAndConsumeDragClick(map);
    const draggedRotation = map.getAttribute('data-rotation');
    expect(draggedRotation).not.toBe('[0,0,12]');
    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    expect(map.getAttribute('data-rotation')).toBe(draggedRotation);
    expect(drawerToggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.body.querySelector('.country-insight-popover')).toBeNull();
    expect([...container.querySelectorAll('button')].some((button) => /mundo/i.test(
      `${button.textContent} ${button.getAttribute('aria-label') || ''}`
    ))).toBe(false);
  });

  it('keeps reference-country clicks from resetting the globe or closing the drawer', async () => {
    await renderPage();
    const map = container.querySelector('[data-projection="geoOrthographic"]');
    const toggle = await openDrawer();
    map.setPointerCapture = vi.fn();
    const graticule = container.querySelector('[data-globe-graticule="true"]');
    await dispatchPointerEvent(graticule, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'lostpointercapture', { clientX: 30, clientY: 10 });
    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    expect(map.setPointerCapture).toHaveBeenCalledWith(1);
    const rotation = map.getAttribute('data-rotation');
    for (const id of ['152', '246']) {
      await act(async () => container.querySelector(`[data-geography-id="${id}"]`)
        .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
      expect(map.getAttribute('data-rotation')).toBe(rotation);
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(document.body.querySelector('.country-insight-popover')).toBeNull();
    }
  });

  it('keeps all geography neutral without pins, labels, country-result controls, flags or heat scale', async () => {
    await renderPage();
    expect(container.querySelector('[role="region"]').getAttribute('aria-label'))
      .toBe('Globo de referencia geográfica');
    expect(container.querySelector('.ancestria-map-scale')).toBeNull();
    expect(container.querySelectorAll('[data-globe-pin], [data-globe-label], path[role="button"]'))
      .toHaveLength(0);
    for (const country of container.querySelectorAll('[data-geography-id]')) {
      expect(country.getAttribute('fill')).toBe('#3E5C76');
      expect(country.hasAttribute('tabindex')).toBe(false);
      expect(country.hasAttribute('aria-pressed')).toBe(false);
      await act(async () => {
        country.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        country.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
        country.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      });
    }
    await openDrawer();
    expect(container.querySelectorAll('[data-globe-pin], [data-globe-label]')).toHaveLength(0);
    expect(container.querySelectorAll('.ancestria-insight-legend button, img[src*="flagcdn"]'))
      .toHaveLength(0);
    expect(document.body.querySelector('.country-insight-popover')).toBeNull();
  });

  it('keeps neutral status and reference-only geography visible outside the closed drawer', async () => {
    await renderPage();
    expectNeutralCopy();
    expect(container.querySelector('.ancestria-results-disclosure')).toBeNull();
    expect(getResultStatus().closest('[inert], [aria-hidden="true"]')).toBeNull();
    expect(getResultStatus().getAttribute('role')).toBe('status');
    expect(getResultStatus().getAttribute('aria-live')).toBe('polite');
    expect(getResultStatus().textContent).toContain('La geografía es solo exploración; no interpreta estos resultados');
    expect(getResultStatus().closest('#ancestria-insight-panel')).toBeNull();
    expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-results-status', 'overflow-y')).toBe('auto');
  });

  it('preserves raw component order, fractional values and abstract lengths without demographic conversion', async () => {
    const results = createResults();
    results.results[0].payload.display.components = [
      { label: 'Demo group B', display_percentage: 39.875 },
      { label: 'Demo group A', display_percentage: 60.125 },
    ];
    const local = results.results[1].payload.display;
    local.axis.extent = 200;
    local.segments = [
      { label: 'Demo group B', offset: 0, length: 125 },
      { label: 'Demo group A', offset: 125, length: 75 },
    ];
    mockApi({ results });
    await renderPage();
    await openDrawer();
    expect([...getGlobalSection().querySelectorAll('li')].map((row) => row.textContent))
      .toEqual(['Grupo B: 39.875%', 'Grupo A: 60.125%']);
    expect(getLocalSection().textContent).toContain('Extensión: 200 unidades');
    expect([...getLocalSection().querySelectorAll('li')].map((row) => row.textContent)).toEqual([
      'Grupo B: inicio 0 · longitud 125 unidades',
      'Grupo A: inicio 125 · longitud 75 unidades',
    ]);
    expect(getLocalSection().textContent).not.toContain('%');
    expectNeutralCopy();
  });

  it.each(['global_ancestry', 'local_ancestry', 'both', 'other-only'])(
    'reports unavailable modules honestly: %s', async (missing) => {
      const results = createResults();
      results.results = results.results.filter((result) => (
        missing === 'both' || missing === 'other-only'
          ? !['global_ancestry', 'local_ancestry'].includes(result.module)
          : result.module !== missing
      ));
      mockApi({ results });
      await renderPage();
      await openDrawer();
      const globalMissing = missing !== 'local_ancestry';
      const localMissing = missing !== 'global_ancestry';
      expect(getGlobalSection().textContent.includes('No hay resultados disponibles para este módulo.'))
        .toBe(globalMissing);
      expect(getLocalSection().textContent.includes('No hay resultados disponibles para este módulo.'))
        .toBe(localMissing);
      expectNeutralCopy();
      if (globalMissing && localMissing) expect(getResultStatus().textContent).toContain('No hay datos');
      expect(container.textContent).not.toMatch(/Demo index|Demo trait|Demo interaction/);
    }
  );

  it('does not fabricate display values for recognized older placeholders', async () => {
    const results = createResults(createService('latest', undefined, '1'));
    results.results = results.results.slice(0, 2).map((result) => {
      const label = `Synthetic ${result.module.replace('_', ' ')} placeholder`;
      return { ...result, payload: {
        module: result.module, label, state: 'not_evaluated',
        synthetic: true, non_clinical: true, clinically_reviewed: false,
        disclaimer: fixtureDisclosure.disclaimer,
        rows: [{ label, state: 'not_evaluated', value: null }],
      } };
    });
    mockApi({ results });
    await renderPage();
    await openDrawer();
    expect(getGlobalSection().textContent).toContain('No hay resultados disponibles para este módulo.');
    expect(getLocalSection().textContent).toContain('No hay resultados disponibles para este módulo.');
    expectNeutralCopy();
    expect(container.textContent).not.toMatch(/60%|40%|Demo axis|Demo group/);
    expect(getResultStatus().textContent).toContain('No hay datos');
  });

  const malformedResults = [
    ['duplicate global module', (data) => data.results.push(structuredClone(data.results[0]))],
    ['duplicate local module', (data) => data.results.push(structuredClone(data.results[1]))],
    ['missing envelope synthetic disclosure', (data) => delete data.synthetic],
    ['clinical envelope', (data) => { data.non_clinical = false; }],
    ['empty disclaimer', (data) => { data.disclaimer = ''; }],
    ['wrong result kind', (data) => { data.results[0].result_type = 'evaluated'; }],
    ['wrong value code', (data) => { data.results[0].value_code = 'EVALUATED'; }],
    ['null payload', (data) => { data.results[0].payload = null; }],
    ['payload module mismatch', (data) => { data.results[0].payload.module = 'traits'; }],
    ['evaluated state', (data) => { data.results[0].payload.state = 'evaluated'; }],
    ['missing payload disclosure', (data) => delete data.results[0].payload.synthetic],
    ['clinically reviewed payload', (data) => { data.results[1].payload.clinically_reviewed = true; }],
    ['not display-only', (data) => { data.results[1].payload.display_only = false; }],
    ['numeric semantics mismatch', (data) => { data.results[0].payload.numeric_semantics = 'ancestry'; }],
    ['null display', (data) => { data.results[0].payload.display = null; }],
    ['wrong global display kind', (data) => { data.results[0].payload.display.kind = 'demo_index'; }],
    ['non-array components', (data) => { data.results[0].payload.display.components = {}; }],
    ['empty components', (data) => { data.results[0].payload.display.components = []; }],
    ['null component', (data) => { data.results[0].payload.display.components[0] = null; }],
    ['demographic label', (data) => { data.results[0].payload.display.components[0].label = 'Chile'; }],
    ['localized input label', (data) => { data.results[0].payload.display.components[0].label = 'Grupo A'; }],
    ['duplicate component label', (data) => {
      data.results[0].payload.display.components[1].label = 'Demo group A';
    }],
    ['coerced percentage', (data) => { data.results[0].payload.display.components[0].display_percentage = '60'; }],
    ['missing percentage', (data) => delete data.results[0].payload.display.components[0].display_percentage],
    ['negative percentage', (data) => { data.results[0].payload.display.components[0].display_percentage = -1; }],
    ['percentage above 100', (data) => { data.results[0].payload.display.components[0].display_percentage = 101; }],
    ['inconsistent sum', (data) => { data.results[0].payload.display.components[0].display_percentage = 50; }],
    ['wrong local display kind', (data) => { data.results[1].payload.display.kind = 'fictional_components'; }],
    ['null axis', (data) => { data.results[1].payload.display.axis = null; }],
    ['chromosome axis', (data) => { data.results[1].payload.display.axis.label = 'Chromosome 1'; }],
    ['localized input axis', (data) => { data.results[1].payload.display.axis.label = 'Eje A'; }],
    ['zero extent', (data) => { data.results[1].payload.display.axis.extent = 0; }],
    ['coerced extent', (data) => { data.results[1].payload.display.axis.extent = '100'; }],
    ['biological unit', (data) => { data.results[1].payload.display.axis.unit = 'base_pairs'; }],
    ['empty segments', (data) => { data.results[1].payload.display.segments = []; }],
    ['null segment', (data) => { data.results[1].payload.display.segments[0] = null; }],
    ['negative offset', (data) => { data.results[1].payload.display.segments[0].offset = -1; }],
    ['coerced length', (data) => { data.results[1].payload.display.segments[0].length = '60'; }],
    ['zero length', (data) => { data.results[1].payload.display.segments[0].length = 0; }],
    ['overlap', (data) => { data.results[1].payload.display.segments[1].offset = 59; }],
    ['overflow', (data) => { data.results[1].payload.display.segments[1].length = 41; }],
    ['gap', (data) => { data.results[1].payload.display.segments[1].offset = 61; }],
    ['incomplete axis coverage', (data) => { data.results[1].payload.display.segments[1].length = 39; }],
  ];
  it.each(malformedResults)('fails closed before showing any ancestry numbers: %s', async (_label, mutate) => {
    const results = createResults();
    mutate(results);
    mockApi({ results });
    await renderPage();
    await waitFor(() => getResultStatus()?.textContent.includes('No fue posible'));
    await openDrawer();
    expect(getResultStatus().getAttribute('role')).toBe('alert');
    expectNeutralCopy();
    expect(container.querySelectorAll('.ancestria-insight-legend li')).toHaveLength(0);
    expect(container.textContent).not.toMatch(/Demo group|Demo axis|60%|40%/);
    expect(getResultStatus().querySelector('button')?.textContent).toBe('Reintentar');
    expect(fetch.mock.calls.some(([url]) => /\/genetics\/(ancestry|indigenous)\//.test(String(url)))).toBe(false);
  });

  it('uses wrapped semantic AnimateIcons and an Ancestría-only Sidebar override', async () => {
    window.innerWidth = 390;
    await renderPage();

    const menuToggle = container.querySelector('.ancestria-dashboard__burger');
    expect(menuToggle.getAttribute('aria-label')).toBe('Abrir menú');
    expect(menuToggle.getAttribute('aria-expanded')).toBe('false');
    expectAnimateIconDecorativeIcon(menuToggle, 'menu');
    const navigation = container.querySelector('[aria-label="Dashboard navigation"]');
    expect(navigation.getAttribute('data-has-icon-overrides')).toBe('true');
    const expectedCategoryIcons = [
      AncestryIcon,
      TraitsIcon,
      PharmacogeneticsIcon,
      DiseaseIcon,
    ];
    const categorySvgs = [...navigation.querySelectorAll('svg')];
    expect(categorySvgs).toHaveLength(expectedCategoryIcons.length);
    categorySvgs.forEach((svg, index) => {
      expect(svg.parentElement?.getAttribute('aria-hidden')).toBe('true');
      expect(getIconGeometry(svg)).toEqual(
        getReferenceIconGeometry(expectedCategoryIcons[index], Number(svg.getAttribute('width')))
      );
    });

    await act(async () => menuToggle.click());
    expect(menuToggle.getAttribute('aria-label')).toBe('Cerrar menú');
    expect(menuToggle.getAttribute('aria-expanded')).toBe('true');
    expectAnimateIconDecorativeIcon(menuToggle, 'x');
  });

  it('opens the mobile sheet from a bottom-centered left-chevron handle and keeps it closable', async () => {
    window.innerWidth = 390;
    await renderPage();

    const toggle = container.querySelector('[aria-controls="ancestria-insight-panel"]');
    const panel = container.querySelector('#ancestria-insight-panel');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.getAttribute('aria-label')).toBe('Abrir panel de ancestría');
    expect(toggle.textContent.trim()).toBe('');
    expectAnimateIconDecorativeIcon(toggle, 'chevrons-left');
    expect(panel.getAttribute('aria-hidden')).toBe('true');

    const toggleSelector = '\\.ancestria-drawer-toggle';
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'position')).toBe('absolute');
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'bottom')).toBe('1rem');
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'left')).toBe('50%');
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'top')).toBe('auto');
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'right')).toBe('auto');
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'transform')).toBe('translateX(-50%)');

    const openToggleSelector = '\\.ancestria-page__chart-card--drawer-open \\.ancestria-drawer-toggle';
    expect.soft(getLastCssDeclaration(ancestryStyles, openToggleSelector, 'bottom')).toBe('min(30rem, 90%)');
    expect.soft(getLastCssDeclaration(ancestryStyles, openToggleSelector, 'left')).toBe('50%');
    expect.soft(getLastCssDeclaration(ancestryStyles, openToggleSelector, 'top')).toBe('auto');
    expect.soft(getLastCssDeclaration(ancestryStyles, openToggleSelector, 'right')).toBe('auto');
    expect.soft(getLastCssDeclaration(ancestryStyles, openToggleSelector, 'transform')).toBe('translateX(-50%)');

    await act(async () => toggle.click());

    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(toggle.getAttribute('aria-label')).toBe('Cerrar panel de ancestría');
    expectAnimateIconDecorativeIcon(toggle, 'chevron-down');
    expect(panel.getAttribute('aria-hidden')).toBe('false');
    expect(panel.classList.contains('ancestria-insight-rail--open')).toBe(true);

    await act(async () => toggle.click());
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expectAnimateIconDecorativeIcon(toggle, 'chevrons-left');
    expect(panel.getAttribute('aria-hidden')).toBe('true');
  });

  it('retains the desktop side-drawer handle direction', async () => {
    window.innerWidth = 1280;
    await renderPage();

    const toggle = container.querySelector('[aria-controls="ancestria-insight-panel"]');
    const closedIcon = expectAnimateIconDecorativeIcon(toggle, 'chevrons-left');

    await act(async () => toggle.click());
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const openIcon = expectAnimateIconDecorativeIcon(toggle, 'chevron-right');
    expect(openIcon.outerHTML).not.toBe(closedIcon.outerHTML);
  });

  it('keeps hover free of tooltip metadata and never opens genetic country details', async () => {
    await renderPage();
    const chile = container.querySelector('[data-geography-id="152"]');
    await act(async () => chile.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    expect(chile.hasAttribute('data-tooltip-id')).toBe(false);
    expect(chile.hasAttribute('data-tooltip-content')).toBe(false);
    expect(container.querySelector('[role="tooltip"]')).toBeNull();
    await act(async () => chile.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    expect(document.body.querySelector('.country-insight-popover')).toBeNull();
  });

  it('keeps the expanded mobile sheet and both localized result sections reachable', async () => {
    window.innerWidth = 390;
    await renderPage();
    const toggle = await openDrawer();
    const panel = container.querySelector('#ancestria-insight-panel');
    expect(container.querySelector('.ancestria-dashboard__burger')).not.toBeNull();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(panel.classList.contains('ancestria-insight-rail--open')).toBe(true);
    expect(panel.hasAttribute('inert')).toBe(false);
    expect(getGlobalSection().closest('.ancestria-insight-legend')).not.toBeNull();
    expect(getLocalSection().closest('.ancestria-insight-legend')).not.toBeNull();
    expect(getGlobalSection().textContent).toContain('Grupo A: 60%');
    expect(getLocalSection().textContent).toContain('longitud 60 unidades');
    expectNeutralCopy();
  });

  it('keeps the map and loading status visible before profile and normalized results settle', async () => {
    const list = deferred();
    const profile = deferred();
    mockApi({ services: list.promise, profile: profile.promise });
    await renderPage();
    expect(getResultStatus().textContent).toContain('Cargando');
    expect(getResultStatus().getAttribute('role')).toBe('status');
    expect(getResultStatus().getAttribute('aria-live')).toBe('polite');
    expect(getResultStatus().getAttribute('aria-busy')).toBe('true');
    expect(getResultStatus().textContent).toContain('Cargando datos…');
    expect(getResultStatus().querySelector('button')).toBeNull();
    expectNeutralCopy();
    expect(getResultStatus().closest('[inert], [aria-hidden="true"]')).toBeNull();
    expect(container.querySelector('.ancestria-page__chart-card')).not.toBeNull();
    await act(async () => list.resolve(reply({ error: 'unavailable' }, 500)));
    await waitFor(() => getResultStatus()?.getAttribute('role') === 'alert');
    expect(getResultStatus().textContent).toContain('No fue posible');
    expect(getResultStatus().querySelector('button')).not.toBeNull();
  });

  it.each(['pending', 'failure'])('loads results independently of a %s profile', async (state) => {
    const profile = state === 'pending' ? deferred().promise : reply({ error: 'profile unavailable' }, 500);
    mockApi({ profile });
    await renderPage();
    await openDrawer();
    expect(getGlobalSection().textContent).toContain('Grupo A: 60%');
    expectNeutralCopy();
    expect(getResultStatus().textContent).not.toMatch(/Cargando|No fue posible/);
  });

  it.each(['ready', 'loading', 'permission', 'error', 'empty'])(
    'keeps only retained sidebar destinations when results are %s', async (state) => {
      mockApi(state === 'loading' ? { services: deferred().promise }
        : state === 'permission' ? { listStatus: 403 }
          : state === 'error' ? { listStatus: 500 }
            : state === 'empty' ? { services: [] } : {});
      await renderPage();
      expect([...container.querySelectorAll('nav a')].map((link) => link.getAttribute('href')))
        .toEqual([
          '/dashboard/ancestria', '/dashboard/rasgos',
          '/dashboard/farmacogenetica', '/dashboard/enfermedades',
        ]);
    }
  );

  it('retains profile navigation when normalized results fail', async () => {
    mockApi({ listStatus: 500 });
    await renderPage();
    expect(container.querySelector('[aria-label="Dashboard navigation"]')).not.toBeNull();
    expect(apiRequest.mock.calls.some(([url]) => url === API_ENDPOINTS.ME)).toBe(true);
    expect(getResultStatus().textContent).toContain('No fue posible');
  });

  it.each(['services', 'results'])('keeps the neutral map for an empty %s response', async (resource) => {
    mockApi(resource === 'services' ? { services: [] } : { results: { ...createResults(), results: [] } });
    await renderPage();
    expect(getResultStatus().textContent).toContain('No hay datos');
    expectNeutralCopy();
    expect(getResultStatus().querySelector('button')).not.toBeNull();
    expect(container.querySelector('.ancestria-page__chart-card')).not.toBeNull();
    expect(container.querySelectorAll('.ancestria-insight-legend li')).toHaveLength(0);
    if (resource === 'services') {
      expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/results/'))).toBe(false);
    }
  });

  it.each(['services', 'results'].flatMap((resource) => [401, 403, 404, 500].map((status) => [resource, status])))(
    'exposes a visible retry for %s HTTP %s with the drawer closed', async (resource, status) => {
      mockApi(resource === 'services' ? { listStatus: status } : { resultStatus: status });
      await renderPage();
      const message = getResultStatus();
      expect(message.textContent).toContain(status === 401 || status === 403
        ? 'No tienes permiso' : 'No fue posible');
      expect(message.getAttribute('role')).toBe('alert');
      expect(message.getAttribute('aria-live')).toBe('assertive');
      expectNeutralCopy();
      expect(message.closest('[inert], [aria-hidden="true"]')).toBeNull();
      const retry = message.querySelector('button');
      expect(retry.tagName).toBe('BUTTON');
      expect(retry.getAttribute('type')).toBe('button');
      await act(async () => retry.focus());
      expect(document.activeElement).toBe(retry);
      expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-results-status button:focus-visible', 'outline'))
        .toBe('2px solid #ffffff');
      mockApi();
      // jsdom does not synthesize native button activation from keyboard events.
      // A detail-zero click exercises the browser's native keyboard activation path.
      await act(async () => retry.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 })));
      await waitFor(() => getGlobalSection()?.querySelector('li'));
      expect(getGlobalSection().textContent).toContain('Grupo A: 60%');
      expectNeutralCopy();
      expect(message.textContent).not.toMatch(/No tienes permiso|No fue posible/);
    }
  );

  it('clears stale displays immediately during keyboard retry and leaves them cleared on failure', async () => {
    await renderPage();
    await openDrawer();
    const map = container.querySelector('[data-projection="geoOrthographic"]');
    await rotateGlobeAndConsumeDragClick(map);
    const rotation = map.getAttribute('data-rotation');
    const list = deferred();
    mockApi({ services: list.promise });
    const retry = getResultStatus().querySelector('button');
    await act(async () => {
      retry.focus();
      retry.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }));
    });
    expect(getResultStatus().textContent).toContain('Cargando');
    expect(container.querySelectorAll('.ancestria-insight-legend li')).toHaveLength(0);
    expect(container.textContent).not.toContain('Grupo A');
    expectNeutralCopy();
    expect(map.getAttribute('data-rotation')).toBe(rotation);
    await act(async () => list.resolve(reply({ error: 'unavailable' }, 403)));
    expect(getResultStatus().textContent).toContain('No tienes permiso');
    expect(container.querySelectorAll('.ancestria-insight-legend li')).toHaveLength(0);
  });

  describe('map-only fullscreen', () => {
    it('exposes a labeled, unpressed bottom-right control', async () => {
      await renderPage();

      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;

      expect(button.getAttribute('aria-label')).toMatch(/\S/);
      expect(button.getAttribute('aria-pressed')).toBe('false');
      expectLucideDecorativeIcon(button, ExpandIcon);
      const fullscreenButtonClass = getFullscreenClass(button);
      expect(fullscreenButtonClass).toBeDefined();
      if (!fullscreenButtonClass) return;

      const selector = `\\.${fullscreenButtonClass}`;
      expect(['absolute', 'fixed']).toContain(getLastCssDeclaration(ancestryStyles, selector, 'position'));
      expect(getLastCssDeclaration(ancestryStyles, selector, 'bottom')).toBeDefined();
      expect(getLastCssDeclaration(ancestryStyles, selector, 'right')).toBeDefined();
    });

    it('requests native fullscreen for the map card and synchronizes its pressed state', async () => {
      const fullscreen = installMockFullscreenApi();
      await renderPage();

      const mapCard = container.querySelector('.ancestria-page__chart-card');
      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;

      expect(mapCard.contains(button)).toBe(true);
      await act(async () => button.click());

      expect(fullscreen.requestFullscreen).toHaveBeenCalledTimes(1);
      expect(fullscreen.requestFullscreen.mock.contexts[0]).toBe(mapCard);
      expect(document.fullscreenElement).toBe(mapCard);
      expect(button.getAttribute('aria-pressed')).toBe('true');
      expectLucideDecorativeIcon(button, ShrinkIcon);
      expect(getFullscreenClass(mapCard)).toBeDefined();
      expect(getFullscreenClass(container.querySelector('.ancestria-dashboard'))).toBeUndefined();
    });

    it('exits native fullscreen from the persistent return button', async () => {
      const fullscreen = installMockFullscreenApi();
      await renderPage();

      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;
      await act(async () => button.click());
      expect(button.getAttribute('aria-pressed')).toBe('true');

      await act(async () => button.click());

      expect(fullscreen.exitFullscreen).toHaveBeenCalledTimes(1);
      expect(document.fullscreenElement).toBeNull();
      expect(button.getAttribute('aria-pressed')).toBe('false');
      expectLucideDecorativeIcon(button, ExpandIcon);
      expect(getFullscreenClass(container.querySelector('.ancestria-page__chart-card'))).toBeUndefined();
    });

    it('synchronizes native state after an external browser fullscreen exit', async () => {
      const fullscreen = installMockFullscreenApi();
      await renderPage();

      const mapCard = container.querySelector('.ancestria-page__chart-card');
      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;
      await act(async () => button.click());
      expect(button.getAttribute('aria-pressed')).toBe('true');

      await act(async () => {
        fullscreen.setFullscreenElement(null);
        fullscreen.dispatchFullscreenChange();
      });

      expect(document.fullscreenElement).toBeNull();
      expect(button.getAttribute('aria-pressed')).toBe('false');
      expect(getFullscreenClass(mapCard)).toBeUndefined();
    });

    it.each(['native', 'fallback'])(
      'keeps both localized result sections and neutral geography in %s fullscreen',
      async (mode) => {
        if (mode === 'native') installMockFullscreenApi();
        await renderPage();
        await openDrawer();
        const panel = container.querySelector('#ancestria-insight-panel');
        const mapCard = container.querySelector('.ancestria-page__chart-card');
        if (mode === 'fallback') {
          Object.defineProperty(mapCard, 'requestFullscreen', { configurable: true, value: undefined });
        }
        await act(async () => getFullscreenToggle().click());
        expect(getFullscreenToggle().getAttribute('aria-pressed')).toBe('true');
        expect(panel.classList.contains('ancestria-insight-rail--fullscreen')).toBe(true);
        expect(getGlobalSection().textContent).toContain('Grupo A: 60%');
        expect(getLocalSection().textContent).toContain('longitud 60 unidades');
        expectNeutralCopy();
        expect(panel.querySelectorAll('[role="progressbar"], .ancestria-insight-rail__count, .ancestria-insight-legend__flag'))
          .toHaveLength(0);
        expect(mapCard.querySelectorAll('[data-globe-pin], [data-globe-label]')).toHaveLength(0);
        expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-insight-rail--fullscreen', 'background'))
          .toBe('#f8fbff');
        expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-insight-rail--fullscreen', 'backdrop-filter'))
          .toBe('none');
      }
    );

    it('keeps the fullscreen mobile rail scrollable as a safe-area-aware bottom sheet', async () => {
      window.innerWidth = 390;
      await renderPage();
      await openDrawer();

      const panel = container.querySelector('#ancestria-insight-panel');
      const mapCard = container.querySelector('.ancestria-page__chart-card');
      Object.defineProperty(mapCard, 'requestFullscreen', { configurable: true, value: undefined });
      await act(async () => getFullscreenToggle().click());

      expect(panel.classList.contains('ancestria-insight-rail--fullscreen')).toBe(true);
      expect(panel.querySelector('.ancestria-insight-legend--fullscreen')).not.toBeNull();
      expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-insight-rail--fullscreen', 'border-radius'))
        .toBe('0.9rem 0.9rem 0 0');
      expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-insight-rail--fullscreen', 'padding-bottom'))
        .toBe('calc(1rem + env(safe-area-inset-bottom))');
    });

    it.each(['loading', 'error', 'empty'])(
      'applies the fullscreen rail treatment while ancestry data is %s',
      async (state) => {
        mockApi(state === 'loading' ? { services: deferred().promise }
          : state === 'error' ? { listStatus: 500 } : { services: [] });

        await renderPage();
        const panel = container.querySelector('#ancestria-insight-panel');
        const expectedMessage = state === 'loading'
          ? 'Cargando'
          : state === 'error' ? 'No fue posible' : 'No hay datos';
        await waitFor(() => getResultStatus()?.textContent.includes(expectedMessage));
        await openDrawer();

        const mapCard = container.querySelector('.ancestria-page__chart-card');
        Object.defineProperty(mapCard, 'requestFullscreen', { configurable: true, value: undefined });
        await act(async () => getFullscreenToggle().click());

        expect(panel.classList.contains('ancestria-insight-rail--fullscreen')).toBe(true);
        expect(panel.querySelector('.ancestria-insight-rail__count')).toBeNull();
        expect(panel.querySelector('.ancestria-insight-rail__hint')).toBeNull();
        expect(panel.querySelector('.ancestria-insight-legend__bar')).toBeNull();
      }
    );

    it.each(['loading', 'permission', 'error', 'empty', 'ready'])(
      'keeps neutral copy and %s state reachable inside native fullscreen with the drawer closed',
      async (state) => {
        installMockFullscreenApi();
        mockApi(state === 'loading' ? { services: deferred().promise }
          : state === 'permission' ? { listStatus: 403 }
            : state === 'error' ? { resultStatus: 500 }
              : state === 'empty' ? { services: [] } : {});
        await renderPage();
        await act(async () => getFullscreenToggle().click());
        const root = document.fullscreenElement;
        const message = getResultStatus();
        expect(root.contains(message)).toBe(true);
        expect(message.closest('[inert], [aria-hidden="true"]')).toBeNull();
        expect(root.querySelector('.ancestria-results-disclosure')).toBeNull();
        expectNeutralCopy();
        expect(message.getAttribute('role')).toBe(['permission', 'error'].includes(state) ? 'alert' : 'status');
        expect(message.getAttribute('aria-busy')).toBe(String(state === 'loading'));
        if (state !== 'loading') {
          const retry = message.querySelector('button');
          await act(async () => retry.focus());
          expect(document.activeElement).toBe(retry);
          expect(root.contains(retry)).toBe(true);
        }
      }
    );

    it('uses a fixed map-card-only fallback when the Fullscreen API is unavailable', async () => {
      await renderPage();

      const mapCard = container.querySelector('.ancestria-page__chart-card');
      Object.defineProperty(mapCard, 'requestFullscreen', { configurable: true, value: undefined });
      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;
      await act(async () => button.click());

      const expandedClass = getFullscreenClass(mapCard);
      expect(expandedClass).toBeDefined();
      expect(button.getAttribute('aria-pressed')).toBe('true');
      expectLucideDecorativeIcon(button, ShrinkIcon);
      expect(document.fullscreenElement).toBeNull();
      expect(getLastCssDeclaration(ancestryStyles, `\\.${expandedClass}`, 'position')).toBe('fixed');
      expect(getFullscreenClass(container.querySelector('.ancestria-dashboard'))).toBeUndefined();
      expect(getFullscreenToggle()).toBe(button);

      await act(async () => button.click());
      expect(button.getAttribute('aria-pressed')).toBe('false');
      expect(getFullscreenClass(mapCard)).toBeUndefined();
    });

    it('uses the in-app fallback when a native fullscreen request rejects', async () => {
      const fullscreen = installMockFullscreenApi();
      fullscreen.requestFullscreen.mockRejectedValue(new Error('Fullscreen permission denied'));
      await renderPage();

      const mapCard = container.querySelector('.ancestria-page__chart-card');
      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;
      await act(async () => button.click());
      await waitFor(() => Boolean(getFullscreenClass(mapCard)));

      expect(fullscreen.requestFullscreen.mock.contexts[0]).toBe(mapCard);
      expect(getFullscreenClass(mapCard)).toBeDefined();
      expect(getLastCssDeclaration(ancestryStyles, `\\.${getFullscreenClass(mapCard)}`, 'position'))
        .toBe('fixed');
      expect(button.getAttribute('aria-pressed')).toBe('true');
      expectLucideDecorativeIcon(button, ShrinkIcon);
      expect(document.fullscreenElement).toBeNull();
    });

    it('closes the in-app fallback on Escape', async () => {
      await renderPage();

      const mapCard = container.querySelector('.ancestria-page__chart-card');
      const button = getFullscreenToggle();
      expect(button, 'the map card should expose a fullscreen button').toBeDefined();
      if (!button) return;
      await act(async () => button.click());
      expect(button.getAttribute('aria-pressed')).toBe('true');

      const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
      await act(async () => document.dispatchEvent(escape));

      expect(escape.defaultPrevented).toBe(true);
      expect(button.getAttribute('aria-pressed')).toBe('false');
      expect(getFullscreenClass(mapCard)).toBeUndefined();
    });

    it('keeps the drawer and map handlers untouched when the fullscreen control is clicked', async () => {
      await renderPage();
      const toggle = await openDrawer();
      const mapCard = container.querySelector('.ancestria-page__chart-card');
      const mapClick = vi.fn();
      mapCard.addEventListener('click', mapClick);
      const button = getFullscreenToggle();
      await act(async () => button.click());
      expect(mapClick).not.toHaveBeenCalled();
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(document.body.querySelector('.country-insight-popover')).toBeNull();
    });
  });

  it('does not render the Indigenous section on Ancestria', async () => {
    await renderPage();

    expect(container.querySelector('.indigenous-radar-chart')).toBeNull();
    expect(fetch.mock.calls.some(([url]) => /\/genetics\/indigenous\//.test(String(url)))).toBe(false);
  });
});
