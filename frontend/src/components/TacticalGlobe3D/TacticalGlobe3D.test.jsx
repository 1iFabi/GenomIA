import React, { act } from 'react';
import { readFileSync } from 'node:fs';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TacticalGlobe3D from './TacticalGlobe3D';
import { cwd } from 'node:process';
import { resolve } from 'node:path';

const globeTestFixtures = vi.hoisted(() => ({ topology: null }));
const defaultGeographies = [
  { id: 152, properties: { name: 'Chile' }, center: [-71, -30] },
  { id: 246, properties: { name: 'Finland' }, center: [25, 64] },
  { id: 840, properties: { name: 'United States' }, center: [-100, 40] },
  { id: 484, properties: { name: 'Mexico' }, center: [15, 23] },
  { id: 724, properties: { name: 'Spain' }, center: [-4, 40] },
  { id: '032', properties: { name: 'Argentina' }, center: [-64, -34] },
  { id: 604, properties: { name: 'Peru' }, center: [-75, -9] },
  { id: 380, properties: { name: 'Italy' }, center: [12, 42] },
];
const createTopology = (geographies = defaultGeographies) => {
  const arcs = [];
  const geometries = geographies.map(({ id, properties, center, geometry }) => {
    if (geometry?.type === 'Point') {
      return { type: 'Point', id, properties, coordinates: geometry.coordinates };
    }
    const [longitude, latitude] = center || geometry?.coordinates?.[0]?.[0] || [0, 0];
    const ring = [
      [longitude - 2, latitude - 2],
      [longitude + 2, latitude - 2],
      [longitude + 2, latitude + 2],
      [longitude - 2, latitude + 2],
      [longitude - 2, latitude - 2],
    ];
    const arcIndex = arcs.length;
    arcs.push(ring.map((coordinate, index) => (
      index === 0
        ? coordinate
        : [coordinate[0] - ring[index - 1][0], coordinate[1] - ring[index - 1][1]]
    )));
    return { type: 'Polygon', id, properties, arcs: [[arcIndex]] };
  });
  return {
    type: 'Topology',
    arcs,
    objects: { countries: { type: 'GeometryCollection', geometries } },
  };
};
const createRingTopology = (rings) => ({
  type: 'Topology',
  arcs: rings.map((ring) => ring),
  objects: {
    countries: {
      type: 'GeometryCollection',
      geometries: [{
        type: 'Polygon', id: 152, properties: { name: 'Chile' },
        arcs: [rings.map((_, index) => index)],
      }],
    },
  },
});
const MAX_TEST_RESPONSE_BYTES = 8 * 1024 * 1024;
const createTopologyResponse = (topology, { contentLength, rawText } = {}) => {
  const text = rawText ?? JSON.stringify(topology);
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  const reader = {
    read: vi.fn(async () => {
      if (offset >= bytes.length) return { done: true };
      const value = bytes.subarray(offset, Math.min(offset + 64 * 1024, bytes.length));
      offset += value.length;
      return { done: false, value };
    }),
    cancel: vi.fn(async () => {}),
  };
  return {
    ok: true,
    status: 200,
    headers: { get: (name) => (
      name.toLowerCase() === 'content-length' && contentLength !== undefined
        ? String(contentLength)
        : null
    ) },
    body: { getReader: () => reader, cancel: vi.fn(async () => {}) },
    json: async () => topology,
    reader,
  };
};

const getPathSegments = (path) => [...path.matchAll(/([ML])([\d.-]+),([\d.-]+)|A([\d.-]+),([\d.-]+) 0 ([01]),([01]) ([\d.-]+),([\d.-]+)/g)]
  .map((match) => match[1]
    ? { type: match[1], x: Number(match[2]), y: Number(match[3]) }
    : { type: 'A', radius: Number(match[4]), large: Number(match[6]),
      sweep: Number(match[7]), x: Number(match[8]), y: Number(match[9]) });

const expectHorizon = (point, sphere) => {
  const radius = Number(sphere.getAttribute('r'));
  const centerX = Number(sphere.getAttribute('cx'));
  const centerY = Number(sphere.getAttribute('cy'));
  expect(Math.hypot(point.x - centerX, point.y - centerY)).toBeCloseTo(radius, 1);
};

const globeStyles = readFileSync(
  resolve(cwd(), 'src/components/TacticalGlobe3D/TacticalGlobe3D.css'),
  'utf8'
);
const componentSource = readFileSync(
  resolve(cwd(), 'src/components/TacticalGlobe3D/TacticalGlobe3D.jsx'),
  'utf8'
);

const metadataByGeoId = {
  152: { code: 'CL', name: 'Chile', continent: 'South America' },
  246: { code: 'FI', name: 'Finland', continent: 'Europe' },
  840: { code: 'US', name: 'United States', continent: 'North America' },
  484: { code: 'MX', name: 'Mexico', continent: 'North America' },
  724: { code: 'ES', name: 'Spain', continent: 'Europe' },
  '032': { code: 'AR', name: 'Argentina', continent: 'South America' },
  604: { code: 'PE', name: 'Peru', continent: 'South America' },
  380: { code: 'IT', name: 'Italy', continent: 'Europe' },
};

const countryDataByIso = new Map([
  ['CL', { name: 'Chile', percentage: 42.5, variant_count: 14 }],
  ['FI', { name: 'Finland', percentage: 0 }],
  ['ES', { name: 'Spain', percentage: 21.25 }],
  ['AR', { name: 'Argentina', percentage: 13.5 }],
  ['PE', { name: 'Peru', percentage: 10 }],
  ['IT', { name: 'Italy', percentage: 4.75 }],
]);

const positiveCountryMetadata = (geographies = defaultGeographies) => geographies
  .map((geography) => metadataByGeoId[geography.id])
  .filter((metadata) => {
    const ancestry = metadata && countryDataByIso.get(metadata.code);
    return Number.isFinite(ancestry?.percentage) && ancestry.percentage > 0;
  })
  .sort((left, right) => (
    countryDataByIso.get(right.code).percentage - countryDataByIso.get(left.code).percentage
  ));

let container;
let root;
let originalMatchMedia;
let originalDocumentVisibilityStateDescriptor;

const dispatchPointerEvent = async (target, type, init = {}) => {
  const event = new MouseEvent(type, {
    bubbles: true,
    clientX: init.clientX ?? 0,
    clientY: init.clientY ?? 0,
  });
  Object.defineProperty(event, 'pointerId', { value: init.pointerId ?? 1 });
  if (init.pointerType) Object.defineProperty(event, 'pointerType', { value: init.pointerType });
  await act(async () => target.dispatchEvent(event));
};

const createIntersectionObserverMock = () => {
  let onIntersectionChange = () => {};
  const observer = {
    observe: vi.fn(),
    disconnect: vi.fn(),
    trigger: (isIntersecting) => onIntersectionChange([{ isIntersecting }]),
  };
  const IntersectionObserverMock = vi.fn((callback) => {
    onIntersectionChange = callback;
    return observer;
  });
  vi.stubGlobal('IntersectionObserver', IntersectionObserverMock);
  return { observer, IntersectionObserverMock };
};

const parseCssColor = (value) => {
  const hex = value.match(/^#([\da-f]{3}|[\da-f]{6})$/i)?.[1];
  if (hex) {
    const expanded = hex.length === 3 ? [...hex].map((digit) => digit + digit).join('') : hex;
    return [0, 2, 4].map((offset) => Number.parseInt(expanded.slice(offset, offset + 2), 16));
  }

  const rgb = value.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  return rgb ? rgb.slice(1).map(Number) : null;
};

const contrastRatio = (foreground, background) => {
  const linearize = (channel) => {
    const normalized = channel / 255;
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  };
  const luminance = (color) => {
    const [red, green, blue] = color.map(linearize);
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
};

const approximateSvgTextBounds = (label) => {
  const [translateX, translateY] = label.parentElement
    .getAttribute('transform')
    .match(/translate\(([-\d.]+),\s*([-\d.]+)\)/)
    .slice(1)
    .map(Number);
  const fontSize = Number.parseFloat(window.getComputedStyle(label).fontSize) || 11;
  const textX = translateX + Number(label.getAttribute('x'));
  const baselineY = translateY + Number(label.getAttribute('y'));
  const estimatedWidth = label.textContent.length * fontSize * 0.62;
  const strokeAllowance = Number.parseFloat(label.getAttribute('stroke-width')) / 2 || 1.5;
  const isEndAnchored = label.getAttribute('text-anchor') === 'end';

  return {
    left: (isEndAnchored ? textX - estimatedWidth : textX) - strokeAllowance,
    right: (isEndAnchored ? textX : textX + estimatedWidth) + strokeAllowance,
    top: baselineY - fontSize * 0.85 - strokeAllowance,
    bottom: baselineY + fontSize * 0.2 + strokeAllowance,
  };
};

const renderGlobe = async (overrides = {}) => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  const props = {
    geographyUrl: '/world.json',
    countryDataByIso,
    getGeoCountryInfo: (geography) => metadataByGeoId[geography.id],
    colorScale: (percentage) => `color-${percentage}`,
    selectedCountryCode: null,
    hoveredCountryCode: null,
    onHoverCountry: vi.fn(),
    onSelectCountry: vi.fn(),
    ...overrides,
  };

  await act(async () => root.render(<TacticalGlobe3D {...props} />));
  return { ...props, container };
};

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  originalDocumentVisibilityStateDescriptor = Object.getOwnPropertyDescriptor(
    document,
    'visibilityState'
  );
  originalMatchMedia = window.matchMedia;
  window.matchMedia = vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal('fetch', vi.fn(async () => createTopologyResponse(
    globeTestFixtures.topology || createTopology()
  )));
});

afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container?.remove();
  container = null;
  window.matchMedia = originalMatchMedia;
  if (originalDocumentVisibilityStateDescriptor) {
    Object.defineProperty(document, 'visibilityState', originalDocumentVisibilityStateDescriptor);
  } else {
    delete document.visibilityState;
  }
  globeTestFixtures.topology = null;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('TacticalGlobe3D', () => {
  it('keeps the default accessible name for existing consumers', async () => {
    const { container: globe } = await renderGlobe();
    expect(globe.querySelector('[role="region"]').getAttribute('aria-label'))
      .toBe('Globo de ancestría por país');
  });

  it('accepts a geographic-reference accessible name without changing neutral globe behavior', async () => {
    const { container: globe } = await renderGlobe({
      accessibleLabel: 'Globo de referencia geográfica', countryDataByIso: new Map(),
    });
    expect(globe.querySelector('[role="region"]').getAttribute('aria-label'))
      .toBe('Globo de referencia geográfica');
    expect(globe.querySelectorAll('[data-globe-pin], [data-globe-label], path[role="button"]'))
      .toHaveLength(0);
    expect(globe.querySelector('[data-globe-sphere]')?.getAttribute('fill')).toBe('#F0EBD8');
  });
  it('reuses source great-circle samples across globe rotations', async () => {
    globeTestFixtures.topology = createRingTopology([[
      [0, 0], [10, 0], [10, 10], [0, 10], [0, 0],
    ]]);
    const acos = vi.spyOn(Math, 'acos');
    const { container: globe } = await renderGlobe();
    const tenDegreeDot = Math.cos(10 * Math.PI / 180);
    const sourceEdgeSamples = () => acos.mock.calls.filter(([dot]) => (
      Math.abs(dot - tenDegreeDot) < 1e-10
    )).length;
    const initialSourceSamples = sourceEdgeSamples();
    const map = globe.querySelector('svg');

    expect(initialSourceSamples).toBeGreaterThan(0);
    await dispatchPointerEvent(map, 'pointerdown', { clientX: 100, clientY: 100 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 108, clientY: 100 });

    expect(sourceEdgeSamples()).toBe(initialSourceSamples);
  });

  it('reuses cached geographic vectors during idle rotation projection', async () => {
    vi.useFakeTimers();
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');
    const sine = vi.spyOn(Math, 'sin');
    const cosine = vi.spyOn(Math, 'cos');

    await act(async () => vi.advanceTimersByTime(800));
    const previousRotation = map.getAttribute('data-rotation');
    const callsBeforeRotation = sine.mock.calls.length + cosine.mock.calls.length;
    await act(async () => vi.advanceTimersByTime(250));
    const callsDuringRotation = sine.mock.calls.length + cosine.mock.calls.length
      - callsBeforeRotation;

    expect(map.getAttribute('data-rotation')).not.toBe(previousRotation);
    expect(callsDuringRotation).toBeLessThan(5000);
  });

  it('coalesces drag projection updates to one animation frame and flushes the final pointer position', async () => {
    let scheduledFrame;
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      scheduledFrame = callback;
      return 97;
    });
    const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame');
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');

    const dispatchDragEvent = (type, clientX, clientY) => {
      const event = new MouseEvent(type, { bubbles: true, clientX, clientY });
      Object.defineProperty(event, 'pointerId', { value: 1 });
      map.dispatchEvent(event);
    };
    await act(async () => {
      dispatchDragEvent('pointerdown', 100, 100);
      dispatchDragEvent('pointermove', 108, 100);
      dispatchDragEvent('pointermove', 120, 100);
      dispatchDragEvent('pointermove', 130, 100);
    });

    expect(requestFrame).toHaveBeenCalledTimes(1);
    expect(map.getAttribute('data-rotation')).toBe('[0,0,12]');
    await dispatchPointerEvent(map, 'pointerup', { clientX: 130, clientY: 100 });

    expect(map.getAttribute('data-rotation')).toBe('[-18,0,12]');
    expect(cancelFrame).toHaveBeenCalledWith(97);
    expect(scheduledFrame).toEqual(expect.any(Function));
  });

  it('rejects malformed topology structures before rendering decoded geometry', async () => {
    const topology = createTopology();
    topology.objects.countries.geometries[0].properties = 'invalid-properties';
    globeTestFixtures.topology = topology;
    const { container: globe } = await renderGlobe();

    expect(globe.querySelectorAll('[data-geography-id]')).toHaveLength(0);
  });

  it('rejects topology responses whose declared body size exceeds the limit', async () => {
    const topology = createTopology();
    const response = createTopologyResponse(topology, {
      contentLength: MAX_TEST_RESPONSE_BYTES + 1,
    });
    fetch.mockResolvedValueOnce(response);
    const { container: globe } = await renderGlobe();

    expect(response.reader.read).not.toHaveBeenCalled();
    expect(response.body.cancel).toHaveBeenCalled();
    expect(globe.querySelectorAll('[data-geography-id]')).toHaveLength(0);
  });

  it('rejects topology responses whose streamed body exceeds the limit', async () => {
    const topology = createTopology();
    const json = JSON.stringify(topology);
    const response = createTopologyResponse(topology, {
      rawText: `${json}${' '.repeat(MAX_TEST_RESPONSE_BYTES + 1 - json.length)}`,
    });
    fetch.mockResolvedValueOnce(response);
    const { container: globe } = await renderGlobe();

    expect(response.reader.cancel).toHaveBeenCalled();
    expect(globe.querySelectorAll('[data-geography-id]')).toHaveLength(0);
  });

  it('aborts stale geography requests after URL changes and on unmount', async () => {
    const { container: globe, ...props } = await renderGlobe();
    expect(globe.querySelector('svg')).not.toBeNull();
    const firstSignal = fetch.mock.calls[0][1]?.signal;

    await act(async () => root.render(
      <TacticalGlobe3D {...props} geographyUrl="/replacement-world.json" />
    ));
    const secondSignal = fetch.mock.calls[1][1]?.signal;
    expect(firstSignal?.aborted).toBe(true);

    await act(async () => root.unmount());
    root = null;
    expect(secondSignal?.aborted).toBe(true);
  });

  it('renders the local orthographic SVG with the specified ocean and country colors', async () => {
    const { container: globe } = await renderGlobe();
    const countryPaths = [...globe.querySelectorAll('[data-geography-id]')];

    expect(globe.querySelector('[data-projection="geoOrthographic"]')).not.toBeNull();
    expect(globe.querySelector('svg').getAttribute('data-rotation')).toBe('[0,0,12]');
    const ocean = globe.querySelector('[data-globe-sphere="true"]');
    expect(ocean?.tagName.toLowerCase()).toBe('circle');
    expect(ocean.getAttribute('fill')).toBe('#F0EBD8');
    expect(globe.querySelector('[data-globe-graticule="true"]')).not.toBeNull();
    expect(countryPaths.length).toBeGreaterThan(0);
    expect(countryPaths.every((path) => path.getAttribute('d')?.startsWith('M'))).toBe(true);
    expect(countryPaths.map((path) => [
      path.getAttribute('data-geography-id'),
      path.getAttribute('fill'),
    ])).toEqual([
      ['152', '#1D2D44'],
      ['246', '#3E5C76'],
      ['840', '#3E5C76'],
      ['484', '#3E5C76'],
      ['724', '#1D2D44'],
      ['032', '#1D2D44'],
      ['604', '#1D2D44'],
      ['380', '#1D2D44'],
    ]);
    expect(countryPaths.map((path) => path.getAttribute('stroke')))
      .toEqual(Array(countryPaths.length).fill('#748CAB'));
  });

  it('decodes synthetic TopoJSON arcs into SVG country paths without forbidden renderers', async () => {
    const { container: globe } = await renderGlobe();
    const chile = globe.querySelector('[data-geography-id="152"]');

    expect(componentSource).not.toMatch(/from\s+['"](?:react-simple-maps|d3-geo)['"]/);
    expect(chile).not.toBeNull();
    expect(chile.getAttribute('d')).toMatch(/^M[-\d.]+,[-\d.]+L/);
    expect(globe.querySelector('[data-globe-graticule="true"]')).not.toBeNull();
  });

  it('matches the map-only Framer globe treatment without replacing Ancestría semantics', async () => {
    const { container: globe } = await renderGlobe();
    const svg = globe.querySelector('svg');
    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    const stars = [...globe.querySelectorAll('[data-globe-star]')];
    const radius = Number(sphere.getAttribute('r'));
    const centerX = Number(sphere.getAttribute('cx'));
    const centerY = Number(sphere.getAttribute('cy'));

    expect(svg.getAttribute('viewBox')).toBe('0 0 600 600');
    expect(radius).toBeGreaterThan(270);
    expect(radius + Number(sphere.getAttribute('stroke-width')) / 2).toBeLessThanOrEqual(300);
    expect(stars).toHaveLength(70);
    expect(stars.every((star) => {
      const distance = Math.hypot(
        Number(star.getAttribute('cx')) - centerX,
        Number(star.getAttribute('cy')) - centerY
      );
      return distance > radius + 12;
    })).toBe(true);
    expect(globe.querySelector('#tactical-globe-linear-shading')).not.toBeNull();
    expect(globe.querySelector('#tactical-globe-edge-shading')).not.toBeNull();
    expect(globe.querySelector('[data-globe-atmosphere="true"]')).toBeNull();
    expect(globeStyles).toMatch(/\.tactical-globe\s*\{[^}]*background:\s*transparent/s);
    const graticule = globe.querySelector('[data-globe-graticule="true"]');
    expect(graticule?.getAttribute('stroke')).toBe('#FFFFFF');
    expect(Number(graticule?.getAttribute('opacity'))).toBeGreaterThan(0.31);
  });

  it.each([
    [600, 600, false], [600, 600, true],
    [480, 360, false], [480, 360, true],
    [260, 240, true], [40, 36, true],
  ])('keeps sphere and optional atmosphere inside %sx%s with atmosphere %s', async (width, height, showAtmosphere) => {
    const { container: globe } = await renderGlobe({ showAtmosphere });
    const host = globe.querySelector('.tactical-globe');
    vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({ width, height });
    await act(async () => window.dispatchEvent(new Event('resize')));

    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    const atmosphere = globe.querySelector('[data-globe-atmosphere="true"]');
    expect(globe.querySelector('svg').getAttribute('viewBox')).toBe(`0 0 ${width} ${height}`);
    expect(Number(sphere.getAttribute('r'))).toBeGreaterThan(0);
    for (const circle of [sphere, atmosphere].filter(Boolean)) {
      const extent = Number(circle.getAttribute('r')) + Number(circle.getAttribute('stroke-width')) / 2;
      const centerX = Number(circle.getAttribute('cx'));
      const centerY = Number(circle.getAttribute('cy'));
      expect(centerX - extent).toBeGreaterThanOrEqual(-0.01);
      expect(centerX + extent).toBeLessThanOrEqual(width + 0.01);
      expect(centerY - extent).toBeGreaterThanOrEqual(-0.01);
      expect(centerY + extent).toBeLessThanOrEqual(height + 0.01);
    }
  });

  it('measures a responsive viewport and recalculates the source globe radius', async () => {
    const { container: globe } = await renderGlobe();
    const host = globe.querySelector('.tactical-globe');
    vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({
      width: 480,
      height: 360,
      top: 0,
      right: 480,
      bottom: 360,
      left: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    await act(async () => window.dispatchEvent(new Event('resize')));

    const svg = globe.querySelector('svg');
    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    expect(svg.getAttribute('viewBox')).toBe('0 0 480 360');
    expect(sphere.getAttribute('cx')).toBe('240');
    expect(sphere.getAttribute('cy')).toBe('180');
    expect(Number(sphere.getAttribute('r'))).toBeGreaterThan(160);
    expect(Number(sphere.getAttribute('r'))).toBeLessThanOrEqual(180);
  });

  it('decodes transformed reversed arcs and follows the orthographic limb at the horizon', async () => {
    globeTestFixtures.topology = {
      type: 'Topology',
      transform: { scale: [0.1, 0.1], translate: [0, 0] },
      arcs: [[[880, -20], [40, 0], [0, 40], [-40, 0], [0, -40]]],
      objects: {
        countries: {
          type: 'GeometryCollection',
          geometries: [{ type: 'Polygon', id: 152, properties: { name: 'Chile' }, arcs: [[-1]] }],
        },
      },
    };
    const { container: globe } = await renderGlobe();
    const clippedCountry = globe.querySelector('[data-geography-id="152"]');

    expect(clippedCountry).not.toBeNull();
    const segments = getPathSegments(clippedCountry.getAttribute('d'));
    expect(segments.some(({ type }) => type === 'A')).toBe(true);
    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    for (const [index, segment] of segments.entries()) {
      if (segment.type !== 'A') continue;
      expectHorizon(segment, sphere);
      expectHorizon(segments[index - 1], sphere);
    }
  });

  it.each([false, true])('starts a clipped visible-first polygon on the horizon with reversed winding %s', async (reversed) => {
    const ring = [[0, -20], [110, -20], [110, 20], [0, 20], [0, -20]];
    globeTestFixtures.topology = createRingTopology([reversed ? [...ring].reverse() : ring]);
    const { container: globe } = await renderGlobe();
    const segments = getPathSegments(globe.querySelector('[data-geography-id="152"]').getAttribute('d'));
    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    expect(segments[0].type).toBe('M');
    expectHorizon(segments[0], sphere);
    const arcIndex = segments.findIndex(({ type }) => type === 'A');
    expect(arcIndex).toBeGreaterThan(1);
    expectHorizon(segments[arcIndex - 1], sphere);
    expectHorizon(segments[arcIndex], sphere);
    expect(segments[arcIndex].x).toBeCloseTo(segments[0].x, 1);
    expect(segments[arcIndex].y).toBeCloseTo(segments[0].y, 1);
    expect(segments[arcIndex].large).toBe(0);
  });

  it('retains a long limb arc when clipping a polar polygon and does not substitute the short arc', async () => {
    // A north-polar ring crosses the horizon on both sides of the visible hemisphere.
    globeTestFixtures.topology = createRingTopology([[
      [-180, -20], [-135, -20], [-90, -20], [-45, -20], [0, -20],
      [45, -20], [90, -20], [135, -20], [180, -20],
    ]]);
    const { container: globe } = await renderGlobe();
    const path = globe.querySelector('[data-geography-id="152"]');
    expect(path).not.toBeNull();
    const segments = getPathSegments(path.getAttribute('d'));
    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    const arcs = segments.filter(({ type }) => type === 'A');
    expect(arcs).toHaveLength(1);
    expect(arcs[0].large).toBe(1);
    expect(arcs[0].sweep).toBe(0);
    const exit = segments[segments.findIndex(({ type }) => type === 'A') - 1];
    const centerX = Number(sphere.getAttribute('cx'));
    const centerY = Number(sphere.getAttribute('cy'));
    const startAngle = Math.atan2(exit.y - centerY, exit.x - centerX);
    const endAngle = Math.atan2(arcs[0].y - centerY, arcs[0].x - centerX);
    const sweep = (startAngle - endAngle + 2 * Math.PI) % (2 * Math.PI);
    const middleAngle = startAngle - sweep / 2;
    expect(sweep).toBeGreaterThan(Math.PI);
    expect(Math.sin(middleAngle)).toBeLessThan(-0.5);
    expectHorizon(arcs[0], sphere);
    expectHorizon(segments[segments.findIndex(({ type }) => type === 'A') - 1], sphere);
  });

  it('stitches separate visible runs into closed horizon-bounded polygon contours', async () => {
    globeTestFixtures.topology = createRingTopology([[
      [-95, -40], [0, -40], [95, -40], [95, 40],
      [0, 40], [-95, 40], [-95, -40],
    ]]);
    const { container: globe } = await renderGlobe();
    const path = globe.querySelector('[data-geography-id="152"]').getAttribute('d');
    const segments = getPathSegments(path);
    const sphere = globe.querySelector('[data-globe-sphere="true"]');
    expect(path.match(/M/g)).toHaveLength(1);
    expect(path.match(/Z/g)).toHaveLength(1);
    expect(segments.filter(({ type }) => type === 'A')).toHaveLength(2);
    for (const [index, segment] of segments.entries()) {
      if (segment.type !== 'A') continue;
      expectHorizon(segments[index - 1], sphere);
      expectHorizon(segment, sphere);
    }
  });

  it('keeps clipped polygon holes transparent under evenodd fill and leaves line geometries open', async () => {
    const outer = [[-20, -20], [20, -20], [20, 20], [-20, 20], [-20, -20]];
    const hole = [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]];
    globeTestFixtures.topology = {
      type: 'Topology',
      arcs: [outer, hole, [[0, 0], [110, 0]]],
      objects: { countries: { type: 'GeometryCollection', geometries: [
        { type: 'Polygon', id: 152, properties: { name: 'Chile' }, arcs: [[0], [1]] },
        { type: 'LineString', id: 246, properties: { name: 'Finland' }, arcs: [2] },
      ] } },
    };
    const { container: globe } = await renderGlobe();
    const polygon = globe.querySelector('[data-geography-id="152"]');
    const line = globe.querySelector('[data-geography-id="246"]');
    expect(polygon.getAttribute('fill-rule')).toBe('evenodd');
    expect(polygon.getAttribute('d').match(/M/g)).toHaveLength(2);
    expect(polygon.getAttribute('d').match(/Z/g)).toHaveLength(2);
    expect(line.getAttribute('d')).not.toMatch(/[AZ]/);
    expect(line.getAttribute('d')).toMatch(/^M.*L/);
  });

  it('uses source-compatible orthographic axes and drag sensitivity', async () => {
    globeTestFixtures.topology = createTopology([
      { id: 152, properties: { name: 'Chile' }, geometry: { type: 'Point', coordinates: [0, 0] } },
    ]);
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');
    const pin = globe.querySelector('[data-globe-pin="CL"]');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 100, clientY: 100 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 120, clientY: 100 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 120, clientY: 100 });

    expect(map.getAttribute('data-rotation')).toBe('[-12,0,12]');
    const pinPosition = pin.parentElement.getAttribute('transform')
      .match(/translate\(([-\d.]+), ([-\d.]+)\)/).slice(1).map(Number);
    const radius = Number(globe.querySelector('[data-globe-sphere="true"]').getAttribute('r'));
    expect(pinPosition[0]).toBeCloseTo(300 + radius * Math.sin(12 * Math.PI / 180)
      * Math.cos(12 * Math.PI / 180), 1);
    expect(pinPosition[1]).toBeCloseTo(300 - radius * Math.sin(12 * Math.PI / 180) ** 2, 1);
  });

  it('increases tilt while dragging down and clamps it to the source range', async () => {
    vi.useFakeTimers();
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 100, clientY: 100 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 100, clientY: 120 });
    await act(async () => vi.advanceTimersByTime(20));
    expect(map.getAttribute('data-rotation')).toBe('[0,12,12]');
    await dispatchPointerEvent(map, 'pointermove', { clientX: 100, clientY: 400 });
    await act(async () => vi.advanceTimersByTime(20));
    expect(map.getAttribute('data-rotation')).toBe('[0,85,12]');
  });

  it('renders positive-only locators with a blue pulse and coral halo', async () => {
    const { container: globe } = await renderGlobe();
    const pins = [...globe.querySelectorAll('[data-globe-pin]')];

    expect(pins.map((pin) => pin.getAttribute('data-globe-pin')))
      .toEqual(['CL', 'ES', 'AR', 'PE', 'IT']);
    expect(globe.querySelector('[data-globe-pin="FI"]')).toBeNull();
    expect(globe.querySelector('[data-globe-pin="US"]')).toBeNull();

    const chilePin = globe.querySelector('[data-globe-pin="CL"]');
    const [pulse, , , highlight] = [...chilePin.children];
    expect([...chilePin.children].map((layer) => layer.tagName.toLowerCase()))
      .toEqual(['circle', 'circle', 'circle', 'circle']);
    expect([...chilePin.children].map((layer) => [
      layer.getAttribute('r'),
      layer.getAttribute('fill'),
    ])).toEqual([
      ['7', '#0b77cc'],
      ['10.5', 'rgba(229,62,62,0.14)'],
      ['5', '#0b77cc'],
      ['1.75', 'rgba(255,255,255,0.55)'],
    ]);
    expect(highlight.getAttribute('cx')).toBe('-1.75');
    expect(highlight.getAttribute('cy')).toBe('-1.75');

    expect(pulse.classList.contains('tactical-globe__pin-pulse')).toBe(true);
    const pulseStyle = globeStyles.match(/\.tactical-globe__pin-pulse\s*\{([^}]*)\}/s)?.[1] || '';
    expect(pulseStyle).toMatch(/animation:\s*tactical-globe-pin-pulse\s+2\.4s\s+ease-out\s+infinite/);
    expect(globeStyles).toMatch(/@keyframes\s+tactical-globe-pin-pulse/);
    expect(globeStyles).toMatch(/0%,\s*100%\s*\{[^}]*transform:\s*scale\(1\)[^}]*opacity:\s*0\.55[^}]*\}/s);
    expect(globeStyles).toMatch(/50%\s*\{[^}]*transform:\s*scale\(1\.6\)[^}]*opacity:\s*0\.05[^}]*\}/s);
  });

  it('styles name labels with the selected high-contrast dark-globe treatment', async () => {
    const { container: globe } = await renderGlobe();
    const label = globe.querySelector('[data-globe-label="CL"]');
    const labelStrokeColor = parseCssColor('#444444');
    const oceanColor = parseCssColor('#F0EBD8');

    expect(label).not.toBeNull();
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*fill:\s*#E7ECE9[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*stroke:\s*#444444[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*stroke-width:\s*3px[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*paint-order:\s*stroke[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*font-family:\s*['"]?SF Mono[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*font-size:\s*10px[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*font-weight:\s*600[^}]*\}/s);
    expect(globeStyles).toMatch(/\.tactical-globe__label\s*\{[^}]*letter-spacing:\s*0\.04em[^}]*\}/s);
    expect(label.getAttribute('x')).toBe('11');
    expect(label.getAttribute('y')).toBe('3');
    expect(globeStyles).not.toMatch(/\.ancestria-map-country:hover\s*\{/);
    expect(globeStyles).toMatch(/transition:\s*fill 140ms ease,\s*filter 140ms ease/);
    expect(contrastRatio(labelStrokeColor, oceanColor)).toBeGreaterThanOrEqual(4.5);
  });

  it('does not turn globe rotation into hover or tooltip state and retains country focus', async () => {
    const onHoverCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onHoverCountry });
    const chile = globe.querySelector('[data-geography-id="152"]');

    expect(chile.hasAttribute('data-tooltip-id')).toBe(false);
    expect(chile.hasAttribute('data-tooltip-content')).toBe(false);
    await act(async () => {
      chile.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      chile.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }));
    });

    expect(onHoverCountry).not.toHaveBeenCalled();
    expect(chile.getAttribute('stroke')).toBe('#748CAB');
    await act(async () => chile.focus());
    expect(onHoverCountry).toHaveBeenCalledWith('CL');
    expect(chile.getAttribute('role')).toBe('button');
    expect(chile.getAttribute('tabindex')).toBe('0');
  });

  it('removes pointer focus rectangles while retaining a path-shaped keyboard focus cue', () => {
    const rules = [...globeStyles.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
    const pointerFocusRule = rules.find(([, selector]) => (
      selector.includes('.ancestria-map-country')
      && /:focus\b/.test(selector)
      && /:not\(\s*:focus-visible\s*\)/.test(selector)
    ))?.[2] || '';
    const keyboardFocusRule = rules.find(([, selector]) => (
      selector.includes('.ancestria-map-country')
      && /:focus-visible\b/.test(selector)
      && !/:not\(\s*:focus-visible\s*\)/.test(selector)
    ))?.[2] || '';

    expect(pointerFocusRule).toMatch(/outline:\s*(?:none|0)\b/i);
    expect(keyboardFocusRule).toMatch(/outline:\s*(?:none|0)\b/i);
    expect(keyboardFocusRule).toMatch(/(?:stroke(?:-width)?|filter)\s*:/i);
  });

  it('keeps persistent name-only labels for every positive ancestry country', async () => {
    const { container: globe } = await renderGlobe();
    const labels = [...globe.querySelectorAll('[data-globe-label]')];
    const expected = positiveCountryMetadata();

    expect(labels.map((label) => label.getAttribute('data-globe-label')))
      .toEqual(expected.map((metadata) => metadata.code));
    expect(labels.map((label) => label.textContent))
      .toEqual(expected.map((metadata) => metadata.name));
    expect(labels.every((label) => !/%|\d/.test(label.textContent))).toBe(true);
    expect(globe.querySelector('[data-globe-label="FI"]')).toBeNull();
    expect(globe.querySelector('[data-globe-label="US"]')).toBeNull();
    expect(globe.querySelector('[data-globe-label="MX"]')).toBeNull();
  });

  it('keeps all visible positive country-name labels readable when centroids are near-collocated', async () => {
    const geographies = [
      { id: 152, properties: { name: 'Chile' }, geometry: { type: 'Point', coordinates: [0, 0] } },
      { id: 724, properties: { name: 'Spain' }, geometry: { type: 'Point', coordinates: [0.1, 0] } },
      { id: '032', properties: { name: 'Argentina' }, geometry: { type: 'Point', coordinates: [0.2, 0] } },
    ];
    globeTestFixtures.topology = createTopology(geographies);

    const { container: globe } = await renderGlobe();
    const labels = [...globe.querySelectorAll('[data-globe-label]')];
    const labelBounds = labels.map((label) => ({
      name: label.textContent,
      ...approximateSvgTextBounds(label),
    }));
    const overlappingPairs = labelBounds.flatMap((label, index) => (
      labelBounds.slice(index + 1)
        .filter((other) => label.left < other.right
          && other.left < label.right
          && label.top < other.bottom
          && other.top < label.bottom)
        .map((other) => [label.name, other.name])
    ));

    const expected = positiveCountryMetadata(geographies);
    expect(labels.map((label) => label.getAttribute('data-globe-label')))
      .toEqual(expected.map((metadata) => metadata.code));
    expect(labels.map((label) => label.textContent))
      .toEqual(expected.map((metadata) => metadata.name));
    expect(labels.every((label) => !/%|\d/.test(label.textContent))).toBe(true);
    expect(overlappingPairs).toEqual([]);
  });

  it('keeps zero and missing ancestry countries unlabeled after hover or focus', async () => {
    const { container: globe } = await renderGlobe();
    const expected = positiveCountryMetadata();
    const zeroCountry = globe.querySelector('[data-geography-id="246"]');
    const missingCountries = [
      globe.querySelector('[data-geography-id="840"]'),
      globe.querySelector('[data-geography-id="484"]'),
    ];

    for (const country of [zeroCountry, ...missingCountries]) {
      await act(async () => {
        country.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        country.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
      });
      expect([...globe.querySelectorAll('[data-globe-label]')]
        .map((label) => label.getAttribute('data-globe-label')))
        .toEqual(expected.map((metadata) => metadata.code));
    }
  });

  it('does not select zero or missing ancestry countries by pointer or keyboard', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const unselectableCountries = [
      globe.querySelector('[data-geography-id="246"]'),
      globe.querySelector('[data-geography-id="840"]'),
      globe.querySelector('[data-geography-id="484"]'),
    ];

    for (const country of unselectableCountries) {
      await act(async () => country.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
      await act(async () => country.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Enter',
        bubbles: true,
        cancelable: true,
      })));
      expect(country.getAttribute('aria-pressed')).not.toBe('true');
    }
    expect(onSelectCountry).not.toHaveBeenCalled();
  });

  it('keeps locator and label overlays passive without intercepting country selection', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry, selectedCountryCode: 'FI' });
    const annotations = globe.querySelector('[data-globe-annotations]');

    expect(annotations).not.toBeNull();
    expect(annotations.getAttribute('aria-hidden')).toBe('true');
    expect(annotations.getAttribute('pointer-events')).toBe('none');
    expect(annotations.querySelectorAll('button, a, [role], [tabindex]')).toHaveLength(0);

    const chile = globe.querySelector('[data-geography-id="152"]');
    await act(async () => chile.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    expect(onSelectCountry).toHaveBeenCalledWith(
      countryDataByIso.get('CL'),
      metadataByGeoId[152],
      expect.objectContaining({ clientX: 0 })
    );
  });

  it('selects countries directly with pointer and keyboard and exposes their names', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const chile = globe.querySelector('[data-geography-id="152"]');

    expect(chile.getAttribute('role')).toBe('button');
    expect(chile.getAttribute('tabindex')).toBe('0');
    expect(chile.getAttribute('aria-label')).toContain('Chile');
    await act(async () => chile.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      clientX: 110,
      clientY: 135,
    })));
    expect(onSelectCountry).toHaveBeenCalledWith(
      countryDataByIso.get('CL'),
      metadataByGeoId[152],
      expect.objectContaining({ clientX: 110, clientY: 135 })
    );

    await act(async () => chile.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    })));
    await act(async () => chile.dispatchEvent(new KeyboardEvent('keydown', {
      key: ' ',
      bubbles: true,
      cancelable: true,
    })));
    expect(onSelectCountry).toHaveBeenCalledTimes(3);
  });

  it('selects a country click without capturing the pointer before dragging', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');
    map.setPointerCapture = vi.fn();

    await dispatchPointerEvent(chile, 'pointerdown', { clientX: 40, clientY: 50 });
    await dispatchPointerEvent(chile, 'pointerup', { clientX: 40, clientY: 50 });
    await act(async () => chile.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      clientX: 40,
      clientY: 50,
      detail: 1,
    })));

    expect(onSelectCountry).toHaveBeenCalledWith(
      countryDataByIso.get('CL'),
      metadataByGeoId[152],
      expect.objectContaining({ clientX: 40, clientY: 50 })
    );
    expect(map.setPointerCapture).not.toHaveBeenCalled();
  });

  it('ignores the click after pointerup and lost capture without suppressing later country or background clicks', async () => {
    const onBackgroundClick = vi.fn();
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onBackgroundClick, onSelectCountry });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');
    map.setPointerCapture = vi.fn();

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'lostpointercapture', { clientX: 30, clientY: 10 });
    await act(async () => map.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      clientX: 30,
      clientY: 10,
      detail: 0,
    })));

    expect(map.setPointerCapture).toHaveBeenCalledWith(1);
    expect(onBackgroundClick).not.toHaveBeenCalled();

    await act(async () => chile.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    await act(async () => chile.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    })));
    expect(onSelectCountry).toHaveBeenCalledTimes(2);

    await act(async () => map.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      clientX: 30,
      clientY: 10,
      detail: 1,
    })));

    expect(onBackgroundClick).toHaveBeenCalledTimes(1);
  });

  it('suppresses the native pointer click after capture without swallowing a later background click', async () => {
    const onBackgroundClick = vi.fn();
    const onSelectCountry = vi.fn();
    const props = await renderGlobe({ onBackgroundClick, onSelectCountry });
    const { container: globe, ...globeProps } = props;
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');
    map.setPointerCapture = vi.fn();

    await dispatchPointerEvent(chile, 'pointerdown', {
      clientX: 10,
      clientY: 10,
      pointerType: 'mouse',
    });
    await dispatchPointerEvent(chile, 'pointerup', {
      clientX: 10,
      clientY: 10,
      pointerType: 'mouse',
    });
    const countryClick = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      clientX: 10,
      clientY: 10,
      detail: 1,
    });
    Object.defineProperties(countryClick, {
      pointerId: { value: 1 },
      pointerType: { value: 'mouse' },
    });
    await act(async () => chile.dispatchEvent(countryClick));
    await act(async () => root.render(
      <TacticalGlobe3D {...globeProps} selectedCountryCode="CL" />
    ));

    await dispatchPointerEvent(chile, 'pointerdown', {
      clientX: 10,
      clientY: 10,
      pointerType: 'mouse',
    });
    await dispatchPointerEvent(map, 'pointermove', {
      clientX: 30,
      clientY: 10,
      pointerType: 'mouse',
    });
    await dispatchPointerEvent(map, 'pointerup', {
      clientX: 30,
      clientY: 10,
      pointerType: 'mouse',
    });
    await dispatchPointerEvent(map, 'lostpointercapture', {
      clientX: 30,
      clientY: 10,
      pointerType: 'mouse',
    });

    const dragClick = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      clientX: 30,
      clientY: 10,
      detail: 1,
    });
    Object.defineProperties(dragClick, {
      pointerId: { value: 1 },
      pointerType: { value: 'mouse' },
    });
    await act(async () => map.dispatchEvent(dragClick));

    expect(map.setPointerCapture).toHaveBeenCalledWith(1);
    expect(onSelectCountry).toHaveBeenCalledTimes(1);
    expect(onBackgroundClick).not.toHaveBeenCalled();
    expect(dragClick.defaultPrevented).toBe(false);

    await act(async () => map.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      clientX: 30,
      clientY: 10,
      detail: 1,
    })));

    expect(onBackgroundClick).toHaveBeenCalledTimes(1);
  });

  it('preserves the dragged rotation and notifies the page after a background click', async () => {
    vi.useFakeTimers();
    const onBackgroundClick = vi.fn();
    const { container: globe } = await renderGlobe({ onBackgroundClick });
    const map = globe.querySelector('svg');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    const draggedRotation = map.getAttribute('data-rotation');
    expect(draggedRotation).not.toBe('[0,0,12]');
    expect(onBackgroundClick).not.toHaveBeenCalled();

    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));

    expect.soft(map.getAttribute('data-rotation')).toBe(draggedRotation);
    expect(onBackgroundClick).toHaveBeenCalledTimes(1);
  });

  it('does not reset on country clicks, including countries without API data', async () => {
    vi.useFakeTimers();
    const onSelectCountry = vi.fn();
    const onBackgroundClick = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry, onBackgroundClick });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');
    const unitedStates = globe.querySelector('[data-geography-id="840"]');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    const draggedRotation = map.getAttribute('data-rotation');

    await act(async () => chile.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    expect(onSelectCountry).toHaveBeenCalledTimes(1);
    expect(onBackgroundClick).not.toHaveBeenCalled();
    expect(map.getAttribute('data-rotation')).toBe(draggedRotation);

    await act(async () => unitedStates.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    expect(onSelectCountry).toHaveBeenCalledTimes(1);
    expect(onBackgroundClick).not.toHaveBeenCalled();
    expect(map.getAttribute('data-rotation')).toBe(draggedRotation);
  });

  it('keeps country selection available after losing pointer capture during a drag', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');
    map.setPointerCapture = vi.fn();

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'lostpointercapture', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await act(async () => chile.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));

    expect(map.setPointerCapture).toHaveBeenCalledWith(1);
    expect(onSelectCountry).toHaveBeenCalledTimes(1);
  });

  it('keeps keyboard selection after a completed drag and a background click', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    await act(async () => chile.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    })));

    expect(onSelectCountry).toHaveBeenCalledTimes(1);
  });

  it('consumes drag click suppression on a background click', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointerup', { clientX: 30, clientY: 10 });
    await act(async () => map.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));
    await act(async () => chile.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 })));

    expect(onSelectCountry).toHaveBeenCalledTimes(1);
  });

  it('keeps keyboard selection after a drag is canceled', async () => {
    const onSelectCountry = vi.fn();
    const { container: globe } = await renderGlobe({ onSelectCountry });
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');

    await dispatchPointerEvent(map, 'pointerdown', { clientX: 10, clientY: 10 });
    await dispatchPointerEvent(map, 'pointermove', { clientX: 30, clientY: 10 });
    await dispatchPointerEvent(map, 'pointercancel', { clientX: 30, clientY: 10 });
    await act(async () => chile.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    })));

    expect(onSelectCountry).toHaveBeenCalledTimes(1);
  });

  it('advances only longitude during idle rotation while keeping the fixed tilted axis', async () => {
    vi.useFakeTimers();
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');

    expect(JSON.parse(map.getAttribute('data-rotation'))).toEqual([0, 0, 12]);
    await act(async () => vi.advanceTimersByTime(800));

    const [longitude, latitude, roll] = JSON.parse(map.getAttribute('data-rotation'));
    expect(longitude).toBeGreaterThan(0);
    expect(latitude).toBe(0);
    expect(roll).toBe(12);
  });

  it('continues rotating on pointer hover and after pointer leave', async () => {
    vi.useFakeTimers();
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');
    const initialRotation = map.getAttribute('data-rotation');

    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).not.toBe(initialRotation);

    await dispatchPointerEvent(map, 'pointerover', { relatedTarget: document.body });
    const hoveredRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(500));
    expect(map.getAttribute('data-rotation')).not.toBe(hoveredRotation);

    await dispatchPointerEvent(map, 'pointerout', { relatedTarget: document.body });
    const pointerLeaveRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).not.toBe(pointerLeaveRotation);
  });

  it('pauses rotation for a selected country with positive ancestry', async () => {
    vi.useFakeTimers();
    const { container: globe, ...props } = await renderGlobe();
    const map = globe.querySelector('svg');
    const initialRotation = map.getAttribute('data-rotation');

    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).not.toBe(initialRotation);

    await act(async () => root.render(
      <TacticalGlobe3D {...props} selectedCountryCode="CL" />
    ));
    const selectedRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(500));

    expect(globe.querySelector('[data-geography-id="152"]')?.getAttribute('aria-pressed'))
      .toBe('true');
    expect(map.getAttribute('data-rotation')).toBe(selectedRotation);
  });

  it.each([
    ['zero ancestry', 'FI'],
    ['missing ancestry', 'US'],
  ])('continues rotation for a selected country with %s', async (_label, countryCode) => {
    vi.useFakeTimers();
    const { container: globe, ...props } = await renderGlobe();
    const map = globe.querySelector('svg');

    await act(async () => vi.advanceTimersByTime(800));
    await act(async () => root.render(
      <TacticalGlobe3D {...props} selectedCountryCode={countryCode} />
    ));
    const selectedRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(800));

    expect(map.getAttribute('data-rotation')).not.toBe(selectedRotation);
  });

  it('keeps keyboard-focus interaction available and pauses idle rotation while focused', async () => {
    vi.useFakeTimers();
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');
    const chile = globe.querySelector('[data-geography-id="152"]');

    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).not.toBe('[0,0,12]');
    await act(async () => chile.focus());
    const focusedRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(500));

    expect(document.activeElement).toBe(chile);
    expect(chile.getAttribute('role')).toBe('button');
    expect(map.getAttribute('data-rotation')).toBe(focusedRotation);
  });

  it('pauses hidden-document rotation, cancels its frame, and resumes exactly once', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('IntersectionObserver', undefined);
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
      writable: true,
    });
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame');
    const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame');
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');

    await act(async () => vi.advanceTimersByTime(700));
    expect(map.getAttribute('data-rotation')).toBe('[0,0,12]');
    expect(requestFrame).not.toHaveBeenCalled();

    document.visibilityState = 'visible';
    await act(async () => document.dispatchEvent(new Event('visibilitychange')));
    expect(requestFrame).toHaveBeenCalledTimes(1);
    const firstScheduledFrame = requestFrame.mock.results[0].value;
    await act(async () => document.dispatchEvent(new Event('visibilitychange')));
    expect(requestFrame).toHaveBeenCalledTimes(1);

    document.visibilityState = 'hidden';
    await act(async () => document.dispatchEvent(new Event('visibilitychange')));
    expect(cancelFrame).toHaveBeenCalledTimes(1);
    expect(cancelFrame).toHaveBeenLastCalledWith(firstScheduledFrame);
    const hiddenRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).toBe(hiddenRotation);

    document.visibilityState = 'visible';
    await act(async () => document.dispatchEvent(new Event('visibilitychange')));
    expect(requestFrame).toHaveBeenCalledTimes(2);
    await act(async () => document.dispatchEvent(new Event('visibilitychange')));
    expect(requestFrame).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).not.toBe(hiddenRotation);
  });

  it('pauses offscreen rotation and resumes once when the globe intersects', async () => {
    vi.useFakeTimers();
    const { observer } = createIntersectionObserverMock();
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame');
    const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame');
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');
    const host = globe.querySelector('.tactical-globe');

    expect(observer.observe).toHaveBeenCalledWith(host);
    await act(async () => observer.trigger(false));
    await act(async () => vi.advanceTimersByTime(700));
    expect(map.getAttribute('data-rotation')).toBe('[0,0,12]');
    expect(requestFrame).not.toHaveBeenCalled();

    await act(async () => observer.trigger(true));
    expect(requestFrame).toHaveBeenCalledTimes(1);
    const firstScheduledFrame = requestFrame.mock.results[0].value;
    await act(async () => observer.trigger(true));
    expect(requestFrame).toHaveBeenCalledTimes(1);

    await act(async () => observer.trigger(false));
    expect(cancelFrame).toHaveBeenCalledWith(firstScheduledFrame);
    const offscreenRotation = map.getAttribute('data-rotation');
    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).toBe(offscreenRotation);

    await act(async () => observer.trigger(true));
    expect(requestFrame).toHaveBeenCalledTimes(2);
    await act(async () => observer.trigger(true));
    expect(requestFrame).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTime(800));
    expect(map.getAttribute('data-rotation')).not.toBe(offscreenRotation);
  });

  it('continues idle rotation when IntersectionObserver is unavailable', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('IntersectionObserver', undefined);
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');

    await act(async () => vi.advanceTimersByTime(800));

    expect(map.getAttribute('data-rotation')).not.toBe('[0,0,12]');
  });

  it('unregisters visibility and intersection observers and cancels its pending frame on unmount', async () => {
    vi.useFakeTimers();
    const { observer } = createIntersectionObserverMock();
    const addDocumentListener = vi.spyOn(document, 'addEventListener');
    const removeDocumentListener = vi.spyOn(document, 'removeEventListener');
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame');
    const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame');
    await renderGlobe();

    await act(async () => vi.advanceTimersByTime(700));
    expect(requestFrame).toHaveBeenCalled();
    const pendingFrame = requestFrame.mock.results.at(-1).value;
    const visibilityListener = addDocumentListener.mock.calls.find(([type]) => (
      type === 'visibilitychange'
    ))?.[1];

    await act(async () => root.unmount());
    root = null;

    expect(observer.disconnect).toHaveBeenCalledTimes(1);
    expect(visibilityListener).toEqual(expect.any(Function));
    expect(removeDocumentListener).toHaveBeenCalledWith('visibilitychange', visibilityListener);
    expect(cancelFrame).toHaveBeenCalledWith(pendingFrame);
  });

  it('does not rotate when reduced motion is preferred', async () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { container: globe } = await renderGlobe();
    const map = globe.querySelector('svg');
    const reducedMotionRotation = map.getAttribute('data-rotation');

    await act(async () => vi.advanceTimersByTime(2000));
    expect(map.getAttribute('data-rotation')).toBe(reducedMotionRotation);
  });
});
