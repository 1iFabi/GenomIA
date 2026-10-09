import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cwd } from 'node:process';
import React, { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  BookOpenText as GuideIcon,
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

const disclaimer = 'Resultados de desarrollo. Solo el riesgo monogénico usa datos reales de ClinVar; '
  + 'el resto es simulado y no tiene valor clínico.';
const createResults = () => ({
  service_request_id: 'latest', sample_code: 'SEED-1', disclaimer,
  modules: {
    global_ancestry: [
      { population: 'IBS', label: 'Ibérico', group: 'EUR', group_label: 'Europeo', country_code: 'ES', country: 'España', proportion: 0.6 },
      { population: 'MAP', label: 'Mapuche', group: 'NAT', group_label: 'Amerindio', country_code: 'CL', country: 'Chile', proportion: 0.4 },
    ],
    local_ancestry: [
      { haplotype: 0, contig: '1', start: 1, end: 60_000_000, population: 'EUR', label: 'Europeo', confidence: 0.9 },
      { haplotype: 1, contig: '1', start: 1, end: 40_000_000, population: 'NAT', label: 'Amerindio', confidence: 0.92 },
    ],
  },
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
  services, results = createResults(), listStatus, resultStatus = 200, profile = reply({ user: { id: 1 } }),
} = {}) => {
  fetch.mockImplementation(async (endpoint) => {
    if (endpoint === API_ENDPOINTS.ME) return profile;
    if (endpoint === API_ENDPOINTS.GENOMICS_RESULTS) {
      if (services instanceof Promise) return services;
      if (results instanceof Promise) return results;
      if (Array.isArray(services) && !services.length) return reply({ error: 'No hay resultados disponibles' }, 404);
      return reply(results, listStatus ?? resultStatus);
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
  await waitFor(() => fetch.mock.calls.some(([endpoint]) => endpoint === API_ENDPOINTS.GENOMICS_RESULTS));
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

  it('loads the client results in one request and shows both ancestry modules in API order', async () => {
    const results = createResults();
    const rawResults = structuredClone(results);
    mockApi({ results });
    await renderPage();
    await openDrawer();

    expect(container.querySelector('#ancestria-global-title').textContent).toBe('Tus orígenes');
    // Rows group by the reference country's geographic continent, largest first.
    expect([...getGlobalSection().querySelectorAll('.cx-card')].map((card) => card.getAttribute('aria-label')))
      .toEqual(['Europa: 60.0% de tu genoma, 1 país', 'Sudamérica: 40.0% de tu genoma, 1 país']);
    // The panel carries only global ancestry: no local section and no development note.
    expect(getLocalSection()).toBeNull();
    expect(container.textContent).not.toContain(disclaimer);
    expectNeutralCopy();
    expect(results).toEqual(rawResults);
    expect(getResultStatus()).toBeNull();
    expect(fetch.mock.calls.filter(([url]) => /\/genoma\//.test(String(url)))).toEqual([
      ['/api/genoma/v1/results/', { method: 'GET', credentials: 'include', headers: {} }],
    ]);
  });
  it('lets the map blend into the page without a card surface', () => {
    const selector = '\\.ancestria-page__chart-card';

    expect(getLastCssDeclaration(ancestryStyles, selector, 'background')).toBe('transparent');
    expect(getLastCssDeclaration(ancestryStyles, selector, 'border')).toBe('0');
    expect(getLastCssDeclaration(ancestryStyles, selector, 'box-shadow')).toBe('none');
  });

  it('uses the current globe palette with a bright white graticule', async () => {
    await renderPage();

    const sphere = container.querySelector('[data-globe-sphere="true"]');
    const graticule = container.querySelector('[data-globe-graticule="true"]');

    expect(sphere?.getAttribute('fill')).toBe('#C5DBF0');
    expect(graticule?.getAttribute('stroke')).toBe('#FFFFFF');
    expect(Number(graticule?.getAttribute('opacity'))).toBeGreaterThan(0.31);
    // The overview tints whole continents with ancestry (Europe, South America) and never marks single countries.
    for (const id of ['152', '246', '380', '724', '604']) {
      expect(container.querySelector(`[data-geography-id="${id}"]`)?.getAttribute('fill')).toBe('#6083C5');
    }
    expect(container.querySelector('[data-geography-id="484"]')?.getAttribute('fill')).toBe('#E6E5E0');
    expect(container.querySelectorAll('[data-globe-pin], [data-globe-label]')).toHaveLength(0);
  });

  it('replaces the compass with the rotating coin at the top-left map mark', async () => {
    await renderPage();

    const mapCard = container.querySelector('.ancestria-page__chart-card');
    const mark = mapCard.querySelector('.ancestria-map-mark');
    const coin = mark?.querySelector('.coin-scene .coin');

    expect(mapCard.querySelector('.ancestria-map-compass')).toBeNull();
    expect(coin).not.toBeNull();
    expect(coin?.classList.contains('coin--flat') || coin?.classList.contains('coin--3d')).toBe(true);
    expect(coin?.style.animationDuration).not.toBe('');
    expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'position')).toBe('absolute');
    // Top-left on desktop; mobile hands that corner to the burger and moves the mark right.
    expect(ancestryStyles).toMatch(/\.ancestria-map-mark \{\s*top: 1rem;\s*right: auto;\s*left: 1rem;/);
    expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'right')).toBe('1rem');
  });

  it('keeps the dark map logo visible with the panel open', async () => {
    await renderPage();

    const mapCard = container.querySelector('.ancestria-page__chart-card');
    expect.soft(mapCard.querySelector('.ancestria-map-mark img')).not.toBeNull();
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'filter')).toBe('brightness(0)');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-map-mark', 'top')).toBe('1rem');

    await openDrawer();
    expect.soft(mapCard.querySelector('.ancestria-map-mark img')).not.toBeNull();
  });

  it('explains the globe fills with a legend that follows the level', async () => {
    await renderPage();
    const legend = () => [...container.querySelectorAll('.ancestria-map-legend li')].map((item) => item.textContent);
    expect(legend()).toEqual(['Continente con tu ancestría', 'Sin ancestría registrada']);

    await act(async () => container.querySelector('[data-geography-id="152"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(legend()).toEqual(['Países con tu ancestría', 'Resto de Sudamérica', 'Otros continentes']);
    expect(container.querySelector('.ancestria-map-legend').getAttribute('aria-label')).toBe('Leyenda del mapa');
  });

  it('draws ink-colored map controls with visible focus on the light map', () => {
    const white = parseCssColor('#FFFFFF');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-fullscreen-toggle', 'width')).toBe('48px');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-fullscreen-toggle', 'height')).toBe('48px');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-drawer-toggle', 'width')).toBe('100%');
    for (const className of ['ancestria-drawer-toggle', 'ancestria-fullscreen-toggle']) {
      const selector = `\\.${className}`;
      const foreground = parseCssColor(getLastCssDeclaration(ancestryStyles, selector, 'color'));
      expect.soft(contrastRatio(foreground, white), `${className} icon contrast`).toBeGreaterThanOrEqual(4.5);
      const focusRule = ancestryStyles.split(`.${className}:focus-visible`).at(-1)?.split('}')[0] || '';
      const outline = parseCssColor(focusRule.match(/outline:\s*[^;]+/)?.[0]?.match(/#[\da-f]{3,8}/i)?.[0]);
      expect.soft(outline, `${className} needs a visible focus outline`).not.toBeNull();
      if (outline) expect.soft(contrastRatio(outline, white)).toBeGreaterThanOrEqual(3);
    }
    const border = getLastCssDeclaration(ancestryStyles, '\\.ancestria-fullscreen-toggle', 'border');
    expect.soft(contrastRatio(parseCssColor(border.match(/#[\da-f]{3,8}/i)[0]), white)).toBeGreaterThanOrEqual(3);
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-fullscreen-toggle', 'right')).toBe('1rem');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-fullscreen-toggle', 'bottom')).toBe('1rem');

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
    expect(toggle.textContent).toBe('Ver tus orígenes');
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

  it('colors and enables only the countries present in the client results', async () => {
    await renderPage();
    expect(container.querySelector('[role="region"]').getAttribute('aria-label'))
      .toBe('Globo de ancestría por país');
    expect(container.querySelector('.ancestria-map-scale')).toBeNull();
    const chile = () => container.querySelector('[data-geography-id="152"]');
    expect(chile().getAttribute('aria-label')).toBe('Sudamérica, ver tu ancestría en este continente');
    expect(container.querySelector('[data-geography-id="484"]').hasAttribute('role')).toBe(false);

    await act(async () => chile().dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(container.querySelector('#cx-continent-title').textContent).toBe('Sudamérica');
    expect(chile().getAttribute('fill')).toBe('#203590');
    expect(chile().getAttribute('aria-label')).toContain('40.0%');
    const peru = container.querySelector('[data-geography-id="604"]');
    expect(peru.getAttribute('fill')).toBe('#96B8DB');
    expect(peru.hasAttribute('tabindex')).toBe(false);
    expect(container.querySelector('[data-geography-id="724"]').getAttribute('aria-label'))
      .toBe('Europa, ver tu ancestría en este continente');
    expect([...container.querySelectorAll('[data-globe-pin]')].map((pin) => pin.getAttribute('data-globe-pin')))
      .toEqual(['CL']);

    await act(async () => chile().dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(chile().getAttribute('aria-pressed')).toBe('true');
    expect(container.querySelector('.country-info__name').textContent).toBe('Chile');
    expect(document.body.querySelector('.country-insight-popover')).toBeNull();
  });

  it('steps back to the world view on a click outside the open continent or country', async () => {
    window.innerWidth = 1280;
    await renderPage();
    const map = container.querySelector('[data-projection="geoOrthographic"]');
    const click = (target) => act(async () => target.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    const country = (id) => container.querySelector(`[data-geography-id="${id}"]`);

    await click(country('152'));
    await click(country('604'));
    expect(container.querySelector('#cx-continent-title').textContent).toBe('Sudamérica');
    await click(map);
    expect(getGlobalSection()).not.toBeNull();
    expect(container.querySelector('.cx-crumbs')).toBeNull();

    await click(country('152'));
    await click(country('152'));
    expect([...container.querySelectorAll('.cx-crumbs li')].map((item) => item.textContent))
      .toEqual(['Mundo', 'Sudamérica', 'Chile']);
    await click(country('484'));
    expect(getGlobalSection()).not.toBeNull();
    expect(container.querySelector('[data-geography-id="152"]').getAttribute('fill')).toBe('#6083C5');
  });

  it('removes the status overlay once results are ready', async () => {
    await renderPage();
    expectNeutralCopy();
    expect(getResultStatus()).toBeNull();
    expect(container.textContent).not.toContain('La geografía es solo exploración');
    expect(getLastCssDeclaration(ancestryStyles, '\\.ancestria-results-status', 'overflow-y')).toBe('auto');
  });

  it('walks world, continent and country from the panel and back through the breadcrumb', async () => {
    await renderPage();
    await openDrawer();
    const southAmerica = [...getGlobalSection().querySelectorAll('.cx-card')]
      .find((card) => card.textContent.includes('Sudamérica'));
    await act(async () => southAmerica.click());
    const countries = [...container.querySelectorAll('.cx-country')];
    expect(countries.map((row) => row.getAttribute('aria-label')))
      .toEqual(['Chile, población Mapuche: 40.0% de tu genoma']);
    expect(container.querySelector('.cx-lede').textContent).toContain('40.0%');

    await act(async () => countries[0].click());
    expect(container.querySelector('[data-geography-id="152"]').getAttribute('aria-pressed')).toBe('true');
    expect(container.querySelector('.country-info__name').textContent).toBe('Chile');
    expect([...container.querySelectorAll('.cx-crumbs li')].map((item) => item.textContent))
      .toEqual(['Mundo', 'Sudamérica', 'Chile']);
    expect(container.querySelector('.cx-crumbs [aria-current="page"]').textContent).toBe('Chile');

    const crumb = (label) => [...container.querySelectorAll('.cx-crumbs button')]
      .find((button) => button.textContent === label);
    await act(async () => crumb('Sudamérica').click());
    expect(container.querySelector('#cx-continent-title').textContent).toBe('Sudamérica');
    await act(async () => crumb('Mundo').click());
    expect(getGlobalSection().textContent).toContain('Europa60.0%');
    expect(container.querySelector('#ancestria-insight-panel').classList.contains('ancestria-insight-rail--open')).toBe(true);
  });

  it('opens real country detail from the map and loads the comparison only on demand', async () => {
    window.innerWidth = 390;
    await renderPage();
    const panel = container.querySelector('#ancestria-insight-panel');
    const clickChile = () => act(async () => container.querySelector('[data-geography-id="152"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    await clickChile();
    expect(panel.getAttribute('aria-hidden')).toBe('false');
    await clickChile();
    expect(panel.querySelector('.hook__title').textContent).toBe('Tu lado mapuche');
    expect(panel.querySelector('.hook__region').textContent).toBe('del sur de Chile');
    expect(panel.querySelector('.hook__equiv').textContent).toBe('≈ 1½ de tus 4 abuelos');
    expect(panel.querySelectorAll('.hook-dot--lit, .hook-dot--half')).toHaveLength(2);
    expect(panel.querySelector('.country-info__lead').textContent).toContain('40.0%');
    expect(fetch.mock.calls.some(([url]) => url === API_ENDPOINTS.ANCESTRY_COHORT)).toBe(false);

    fetch.mockImplementation(async (endpoint) => (endpoint === API_ENDPOINTS.ANCESTRY_COHORT
      ? reply({ cohort_size: 3, min_cohort: 10, populations: {} }) : createWorldTopologyResponse()));
    await act(async () => panel.querySelector('#country-tab-comparacion').click());
    await waitFor(() => panel.querySelector('[role="tabpanel"]').textContent.includes('al menos 10'));
    expect(fetch.mock.calls.filter(([url]) => url === API_ENDPOINTS.ANCESTRY_COHORT)).toHaveLength(1);
    expectNeutralCopy();

    await act(async () => panel.querySelector('.cx-crumbs button').click());
    expect(getGlobalSection()).not.toBeNull();
  });

  it('uses wrapped semantic AnimateIcons and the shared animated Sidebar icons', async () => {
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
      GuideIcon,
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

  it('docks the mobile sheet to the screen bottom, lifts the globe into view on open, and closes on Escape', async () => {
    window.innerWidth = 390;
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    await renderPage();

    const toggle = container.querySelector('[aria-controls="ancestria-insight-panel"]');
    const panel = container.querySelector('#ancestria-insight-panel');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.textContent).toBe('Ver tus orígenes');
    expectAnimateIconDecorativeIcon(toggle, 'chevron-up');
    expect(panel.getAttribute('aria-hidden')).toBe('true');

    const toggleSelector = '\\.ancestria-drawer-toggle';
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'position')).toBe('fixed');
    expect.soft(getLastCssDeclaration(ancestryStyles, toggleSelector, 'bottom')).toBe('0');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-page__chart-card \\.ancestria-insight-rail', 'position'))
      .toBe('fixed');
    expect.soft(getLastCssDeclaration(ancestryStyles, '\\.ancestria-page__chart-card--drawer-open \\.ancestria-drawer-toggle',
      'transform')).toBe('translateY(calc(-1 * var(--sheet-h)))');

    await act(async () => toggle.click());
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(toggle.textContent).toBe('Ocultar');
    expectAnimateIconDecorativeIcon(toggle, 'chevron-down');
    expect(panel.getAttribute('aria-hidden')).toBe('false');
    expect(panel.classList.contains('ancestria-insight-rail--open')).toBe(true);
    expect(container.querySelector('.ancestria-dashboard--sheet-open')).not.toBeNull();
    await waitFor(() => scrollIntoView.mock.calls.length > 0);
    expect(scrollIntoView.mock.instances[0]).toBe(container.querySelector('.ancestria-page__chart-card'));

    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })));
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(toggle);
    expectAnimateIconDecorativeIcon(toggle, 'chevron-up');
    expect(panel.getAttribute('aria-hidden')).toBe('true');
    delete Element.prototype.scrollIntoView;
  });

  it('keeps the panel as an always-visible column on desktop', async () => {
    window.innerWidth = 1280;
    await renderPage();

    const panel = container.querySelector('#ancestria-insight-panel');
    expect(container.querySelector('[aria-controls="ancestria-insight-panel"]')).toBeNull();
    expect(panel.getAttribute('aria-hidden')).toBe('false');
    expect(panel.hasAttribute('inert')).toBe(false);
    expect(container.querySelector('[aria-label="Dashboard navigation"]')).not.toBeNull();
    expect(getGlobalSection().textContent).toContain('Europa60.0%');
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
    expect(getGlobalSection().textContent).toContain('Europa60.0%');
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
    expect(getResultStatus().querySelectorAll('.ancestria-loading-summary__row')).toHaveLength(3);
    // While loading, the legend's place holds its skeleton and the panel mirrors the continent cards.
    expect(container.querySelector('.ancestria-map-legend')).toBeNull();
    expect(container.querySelectorAll('.cx-card--skeleton')).toHaveLength(4);
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
    expect(getGlobalSection().textContent).toContain('Europa60.0%');
    expectNeutralCopy();
    expect(getResultStatus()).toBeNull();
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
          '/dashboard/farmacogenetica', '/dashboard/enfermedades', '/dashboard/modulos',
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
    mockApi(resource === 'services' ? { services: [] } : { results: { ...createResults(), modules: {} } });
    await renderPage();
    expect(getResultStatus().textContent).toContain('No hay datos');
    expectNeutralCopy();
    expect(getResultStatus().querySelector('button')).not.toBeNull();
    expect(container.querySelector('.ancestria-page__chart-card')).not.toBeNull();
    expect(container.querySelectorAll('.ancestria-insight-legend li')).toHaveLength(0);
  });

  it.each(['services', 'results'].flatMap((resource) => [401, 403, 500].map((status) => [resource, status])))(
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
        .toBe('2px solid #230462');
      mockApi();
      // jsdom does not synthesize native button activation from keyboard events.
      // A detail-zero click exercises the browser's native keyboard activation path.
      await act(async () => retry.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 })));
      await waitFor(() => getGlobalSection()?.querySelector('li'));
      expect(getGlobalSection().textContent).toContain('Europa60.0%');
      expectNeutralCopy();
      expect(message.textContent).not.toMatch(/No tienes permiso|No fue posible/);
    }
  );

  it('retries a failed load from the keyboard without moving the globe', async () => {
    mockApi({ listStatus: 500 });
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
    expect(container.textContent).not.toContain('Europa60.0%');
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
        expect(getGlobalSection().textContent).toContain('Europa60.0%');
            expectNeutralCopy();
        expect(panel.querySelectorAll('[role="progressbar"], .ancestria-insight-rail__count, .ancestria-insight-legend__flag'))
          .toHaveLength(0);
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

    it.each(['loading', 'permission', 'error', 'empty'])(
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
