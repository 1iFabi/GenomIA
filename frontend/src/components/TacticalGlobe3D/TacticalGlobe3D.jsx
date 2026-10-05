import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './TacticalGlobe3D.css';

const GLOBE_WIDTH = 600;
const GLOBE_HEIGHT = 600;
const OCEAN_COLOR = '#F0EBD8';
const DEFAULT_COUNTRY_STROKE = '#748CAB';
const POSITIVE_COUNTRY_FILL = '#1D2D44';
const NEUTRAL_COUNTRY_FILL = '#3E5C76';
const LOCATOR_PIN_COLOR = '#0b77cc';
const LABEL_FONT_SIZE = 10;
const LABEL_STROKE_ALLOWANCE = 1.5;
const LABEL_COLLISION_GAP = 2;
const ENTRY_REVEAL_MS = 620;
const IDLE_ROTATION_FRAME_INTERVAL_MS = 1000 / 30;
const IDLE_ROTATION_DEGREES_PER_SECOND = 3.5;
const MAX_ROTATION_ELAPSED_MS = 100;
const INITIAL_ROTATION = [0, 0, 12];
const INITIAL_GLOBE_SCALE = 1.08;
const STAR_COUNT = 70;
const STAR_SEED = 1584243068;
const TOPOJSON_COUNTRIES_OBJECT = 'countries';
const MAX_TOPOLOGY_RESPONSE_BYTES = 8 * 1024 * 1024;
const MAX_TOPOLOGY_ARCS = 100_000;
const MAX_TOPOLOGY_ARC_POINTS = 300_000;
const MAX_TOPOLOGY_GEOMETRIES = 20_000;
const MAX_TOPOLOGY_ARC_REFERENCES = 200_000;
const MAX_TOPOLOGY_COORDINATES = 100_000;
const MAX_TOPOLOGY_SAMPLED_POINTS = 1_000_000;
const MAX_GREAT_CIRCLE_SEGMENT_SAMPLES = 60;
const MAX_TOPOLOGY_GEOMETRY_DEPTH = 16;
const COUNTRY_FOCUS_TRANSITION_MS = 520;

const readReducedMotionPreference = () => (
  typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
);

const formatPercentage = (value) => {
  const percentage = Number(value);
  return Number.isFinite(percentage) ? `${percentage.toFixed(1)}%` : null;
};

const hasPositiveAncestry = (countryData) => {
  const percentage = Number(countryData?.percentage);
  return Number.isFinite(percentage) && percentage > 0;
};

const applyTopologyTransform = (position, transform) => {
  if (!transform) return position;
  return [
    position[0] * transform.scale[0] + transform.translate[0],
    position[1] * transform.scale[1] + transform.translate[1],
  ];
};

const isRecord = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isTopologyPosition = (position) => Array.isArray(position)
  && position.length >= 2
  && Number.isFinite(position[0])
  && Number.isFinite(position[1]);

const isValidTopology = (topology) => {
  if (!isRecord(topology) || topology.type !== 'Topology'
    || !Array.isArray(topology.arcs) || topology.arcs.length > MAX_TOPOLOGY_ARCS
    || !isRecord(topology.objects) || !Object.keys(topology.objects).length) return false;

  const transform = topology.transform;
  if (transform && (!isRecord(transform)
    || !Array.isArray(transform.scale) || transform.scale.length !== 2
    || !Array.isArray(transform.translate) || transform.translate.length !== 2
    || ![...transform.scale, ...transform.translate].every(Number.isFinite))) return false;

  let arcPointCount = 0;
  const arcSampleCounts = [];
  const arcEndpoints = [];
  for (const arc of topology.arcs) {
    if (!Array.isArray(arc) || arc.length < 2) return false;
    arcPointCount += arc.length;
    if (arcPointCount > MAX_TOPOLOGY_ARC_POINTS) return false;
    let longitude = 0;
    let latitude = 0;
    let previous = null;
    let start = null;
    let sampleCount = 0;
    for (const position of arc) {
      if (!isTopologyPosition(position)) return false;
      longitude = transform ? longitude + position[0] : position[0];
      latitude = transform ? latitude + position[1] : position[1];
      const coordinate = transform
        ? [longitude * transform.scale[0] + transform.translate[0],
          latitude * transform.scale[1] + transform.translate[1]]
        : position;
      if (!coordinate.every(Number.isFinite)) return false;
      if (previous) {
        const startVector = toVector(previous);
        const endVector = toVector(coordinate);
        const dot = Math.max(-1, Math.min(1, startVector[0] * endVector[0]
          + startVector[1] * endVector[1] + startVector[2] * endVector[2]));
        sampleCount += Math.max(1, Math.ceil(Math.acos(dot) * 180 / Math.PI / 3));
      } else {
        start = coordinate;
      }
      previous = coordinate;
    }
    arcSampleCounts.push(sampleCount);
    arcEndpoints.push({ start, end: previous });
  }

  const arcCount = topology.arcs.length;
  let geometryCount = 0;
  let arcReferenceCount = 0;
  let coordinateCount = 0;
  let estimatedSamplePointCount = 0;
  const validArcSequence = (indexes, closeRing = false) => {
    if (!Array.isArray(indexes) || !indexes.length) return false;
    arcReferenceCount += indexes.length;
    if (arcReferenceCount > MAX_TOPOLOGY_ARC_REFERENCES || !indexes.every((index) => {
      if (!Number.isInteger(index)) return false;
      const resolvedIndex = index < 0 ? ~index : index;
      return resolvedIndex >= 0 && resolvedIndex < arcCount;
    })) return false;

    const resolvedIndexes = indexes.map((index) => (index < 0 ? ~index : index));
    for (let index = 1; index < resolvedIndexes.length; index += 1) {
      const previousArc = arcEndpoints[resolvedIndexes[index - 1]];
      const nextArc = arcEndpoints[resolvedIndexes[index]];
      const previousEnd = indexes[index - 1] < 0 ? previousArc.start : previousArc.end;
      const nextStart = indexes[index] < 0 ? nextArc.end : nextArc.start;
      if (Math.abs(previousEnd[0] - nextStart[0]) > 1e-9
        || Math.abs(previousEnd[1] - nextStart[1]) > 1e-9) return false;
    }

    estimatedSamplePointCount += 1
      + (closeRing ? MAX_GREAT_CIRCLE_SEGMENT_SAMPLES : 0)
      + resolvedIndexes.reduce((sum, index) => sum + arcSampleCounts[index], 0);
    return estimatedSamplePointCount <= MAX_TOPOLOGY_SAMPLED_POINTS;
  };
  const validPosition = (position) => {
    coordinateCount += 1;
    if (coordinateCount > MAX_TOPOLOGY_COORDINATES || !isTopologyPosition(position)) return false;
    if (!transform) return true;
    const transformed = applyTopologyTransform(position, transform);
    return Number.isFinite(transformed[0]) && Number.isFinite(transformed[1]);
  };
  const visitGeometry = (geometry, depth = 0) => {
    geometryCount += 1;
    if (geometryCount > MAX_TOPOLOGY_GEOMETRIES || depth > MAX_TOPOLOGY_GEOMETRY_DEPTH
      || !isRecord(geometry)
      || (geometry.properties !== undefined
        && geometry.properties !== null && !isRecord(geometry.properties))) return false;

    switch (geometry.type) {
      case 'Point':
        return validPosition(geometry.coordinates);
      case 'MultiPoint':
        return Array.isArray(geometry.coordinates)
          && geometry.coordinates.every(validPosition);
      case 'LineString':
        return validArcSequence(geometry.arcs);
      case 'MultiLineString':
        return Array.isArray(geometry.arcs)
          && geometry.arcs.every((line) => validArcSequence(line));
      case 'Polygon':
        return Array.isArray(geometry.arcs)
          && geometry.arcs.every((ring) => validArcSequence(ring, true));
      case 'MultiPolygon':
        return Array.isArray(geometry.arcs)
          && geometry.arcs.every((polygon) => Array.isArray(polygon)
            && polygon.every((ring) => validArcSequence(ring, true)));
      case 'GeometryCollection':
        return Array.isArray(geometry.geometries)
          && geometry.geometries.every((child) => visitGeometry(child, depth + 1));
      default:
        return false;
    }
  };

  return Object.values(topology.objects).every((object) => {
    if (!isRecord(object)) return false;
    return object.type === 'GeometryCollection'
      ? Array.isArray(object.geometries)
        && object.geometries.every((geometry) => visitGeometry(geometry))
      : visitGeometry(object);
  });
};

const readBoundedResponseText = async (response) => {
  const declaredLength = response.headers?.get('content-length');
  if (declaredLength !== null && declaredLength !== undefined) {
    const parsedLength = Number(declaredLength);
    if (!Number.isSafeInteger(parsedLength) || parsedLength < 0
      || parsedLength > MAX_TOPOLOGY_RESPONSE_BYTES) {
      try {
        await response.body?.cancel?.();
      } catch {
        // The body may already be closed by the fetch implementation.
      }
      throw new Error('Globe geography response exceeds the size limit.');
    }
  }

  const reader = response.body?.getReader?.();
  if (!reader) throw new Error('Globe geography response has no readable body.');
  const decoder = new TextDecoder();
  const textChunks = [];
  let receivedBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!ArrayBuffer.isView(value) || value.BYTES_PER_ELEMENT !== 1) {
        throw new Error('Invalid geography response chunk.');
      }
      receivedBytes += value.byteLength;
      if (receivedBytes > MAX_TOPOLOGY_RESPONSE_BYTES) {
        throw new Error('Globe geography response exceeds the size limit.');
      }
      textChunks.push(decoder.decode(value, { stream: true }));
    }
    textChunks.push(decoder.decode());
    return textChunks.join('');
  } catch (error) {
    try {
      await reader.cancel();
    } catch {
      // The reader may already have been canceled by the fetch abort signal.
    }
    throw error;
  }
};

const decodeTopology = (topology) => {
  if (topology?.type !== 'Topology' || !topology.objects) return [];

  const transform = topology.transform;
  const decodedArcs = (topology.arcs || []).map((arc) => {
    let longitude = 0;
    let latitude = 0;
    return arc.map(([deltaLongitude, deltaLatitude]) => {
      if (transform) {
        longitude += deltaLongitude;
        latitude += deltaLatitude;
        return applyTopologyTransform([longitude, latitude], transform);
      }
      return [deltaLongitude, deltaLatitude];
    });
  });

  const decodeArc = (index) => {
    const isReversed = index < 0;
    const arcIndex = isReversed ? ~index : index;
    const arc = decodedArcs[arcIndex] || [];
    return isReversed ? [...arc].reverse() : arc;
  };
  const decodeArcSequence = (indexes) => indexes.flatMap((index, arcIndex) => {
    const points = decodeArc(index);
    return arcIndex === 0 ? points : points.slice(1);
  });
  const decodeCoordinates = (coordinates) => {
    if (Array.isArray(coordinates?.[0])) {
      return coordinates.map((coordinate) => decodeCoordinates(coordinate));
    }
    return applyTopologyTransform(coordinates, transform);
  };

  const decodeGeometry = (geometry) => {
    if (!geometry) return null;
    const { type, properties = {}, id } = geometry;
    let coordinates;
    switch (type) {
      case 'Point':
        coordinates = decodeCoordinates(geometry.coordinates);
        break;
      case 'MultiPoint':
        coordinates = geometry.coordinates.map((point) => decodeCoordinates(point));
        break;
      case 'LineString':
        coordinates = decodeArcSequence(geometry.arcs);
        break;
      case 'MultiLineString':
        coordinates = geometry.arcs.map(decodeArcSequence);
        break;
      case 'Polygon':
        coordinates = geometry.arcs.map(decodeArcSequence);
        break;
      case 'MultiPolygon':
        coordinates = geometry.arcs.map((polygon) => polygon.map(decodeArcSequence));
        break;
      case 'GeometryCollection':
        return geometry.geometries.flatMap((child) => decodeGeometry(child) || []);
      default:
        return null;
    }
    return {
      type: 'Feature',
      ...(id !== undefined ? { id } : {}),
      properties,
      geometry: { type, coordinates },
    };
  };

  const countries = topology.objects[TOPOJSON_COUNTRIES_OBJECT]
    || Object.values(topology.objects).find((object) => object?.type === 'GeometryCollection')
    || Object.values(topology.objects)[0];
  if (!countries) return [];
  const geometries = countries.type === 'GeometryCollection'
    ? countries.geometries
    : [countries];
  return geometries.flatMap((geometry) => {
    const feature = decodeGeometry(geometry);
    return Array.isArray(feature) ? feature : feature ? [feature] : [];
  });
};

const geographicVectorCache = new WeakMap();
const toVector = (position) => {
  const cachedVector = geographicVectorCache.get(position);
  if (cachedVector) return cachedVector;

  const [longitude, latitude] = position;
  const lambda = longitude * Math.PI / 180;
  const phi = latitude * Math.PI / 180;
  const vector = Object.freeze([
    Math.cos(phi) * Math.sin(lambda),
    Math.sin(phi),
    Math.cos(phi) * Math.cos(lambda),
  ]);
  geographicVectorCache.set(position, vector);
  return vector;
};

const fromVector = ([x, y, z]) => [
  Math.atan2(x, z) * 180 / Math.PI,
  Math.atan2(y, Math.hypot(x, z)) * 180 / Math.PI,
];

const interpolateGreatCircle = (from, to, progress) => {
  const start = toVector(from);
  const end = toVector(to);
  const dot = Math.max(-1, Math.min(1, start[0] * end[0] + start[1] * end[1] + start[2] * end[2]));
  const angle = Math.acos(dot);
  if (angle < 1e-7) {
    return [
      from[0] + (to[0] - from[0]) * progress,
      from[1] + (to[1] - from[1]) * progress,
    ];
  }
  const sine = Math.sin(angle);
  const startWeight = Math.sin((1 - progress) * angle) / sine;
  const endWeight = Math.sin(progress * angle) / sine;
  return fromVector([
    start[0] * startWeight + end[0] * endWeight,
    start[1] * startWeight + end[1] * endWeight,
    start[2] * startWeight + end[2] * endWeight,
  ]);
};

const getGlobeRadius = ({ width, height }, showAtmosphere) => {
  // The outer stroke extends beyond the atmosphere's radius by 2.5 units.
  const allowance = showAtmosphere ? 7.5 : 0.55;
  return Math.max(0.01, Math.min(
    Math.min(width - 24, height - 24) / 2 - 8,
    Math.min(width, height) / 2 - allowance
  ));
};

const createStableStars = (width, height, radius) => {
  let seed = STAR_SEED;
  const random = () => {
    let value = seed += 0x6D2B79F5;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 0x100000000;
  };
  const centerX = width / 2;
  const centerY = height / 2;
  const stars = [];
  let attempts = 0;
  while (stars.length < STAR_COUNT && attempts < STAR_COUNT * 1000) {
    attempts += 1;
    const x = random() * width;
    const y = random() * height;
    if (Math.hypot(x - centerX, y - centerY) <= radius + 12) continue;
    stars.push({ x, y, size: 0.4 + random() * 0.9, opacity: 0.18 + random() * 0.6 });
  }
  return stars;
};

const createOrthographicProjector = (rotation, width, height, radius) => {
  const centerX = width / 2;
  const centerY = height / 2;
  const D2R = Math.PI / 180;
  const [lambda, phi, gamma] = rotation;
  const lambdaRadians = lambda * D2R;
  const phiRadians = phi * D2R;
  const gammaRadians = gamma * D2R;
  const lambdaCosine = Math.cos(lambdaRadians);
  const lambdaSine = Math.sin(lambdaRadians);
  const phiCosine = Math.cos(phiRadians);
  const phiSine = Math.sin(phiRadians);
  const gammaCosine = Math.cos(gammaRadians);
  const gammaSine = Math.sin(gammaRadians);

  const project = (coordinates) => {
    const [geographicX, z0, geographicZ] = toVector(coordinates);
    const x0 = geographicZ * lambdaCosine + geographicX * lambdaSine;
    const y0 = geographicX * lambdaCosine - geographicZ * lambdaSine;
    const x1 = x0 * phiCosine + z0 * phiSine;
    const z1 = -x0 * phiSine + z0 * phiCosine;
    const ry = y0 * gammaCosine - z1 * gammaSine;
    const rz = y0 * gammaSine + z1 * gammaCosine;
    return {
      x: centerX + radius * ry,
      y: centerY - radius * rz,
      depth: x1,
      visible: x1 >= 0,
    };
  };
  project.width = width;
  project.height = height;
  project.radius = radius;
  project.centerX = centerX;
  project.centerY = centerY;
  project.centerVector = [
    Math.sin(lambda * D2R) * phiCosine,
    phiSine,
    Math.cos(lambda * D2R) * phiCosine,
  ];
  return project;
};

const formatSvgNumber = (value) => {
  const rounded = Math.round(value * 100) / 100;
  return Object.is(rounded, -0) ? '0' : String(rounded);
};

const sampleLine = (coordinates, closeRing = false, maxStepDegrees = 3) => {
  if (!coordinates?.length) return Object.freeze([]);
  const points = coordinates.filter((point) => point?.length >= 2);
  if (points.length < 2) {
    return Object.freeze(points.map((point) => Object.freeze([...point])));
  }
  const sequence = [...points];
  if (closeRing && (points[0][0] !== points.at(-1)[0] || points[0][1] !== points.at(-1)[1])) {
    sequence.push(points[0]);
  }

  const sampled = [sequence[0]];
  for (let index = 1; index < sequence.length; index += 1) {
    const from = sequence[index - 1];
    const to = sequence[index];
    const startVector = toVector(from);
    const endVector = toVector(to);
    const dot = Math.max(-1, Math.min(1, startVector[0] * endVector[0]
      + startVector[1] * endVector[1] + startVector[2] * endVector[2]));
    const steps = Math.max(1, Math.ceil(Math.acos(dot) * 180 / Math.PI / maxStepDegrees));
    for (let step = 1; step <= steps; step += 1) {
      sampled.push(interpolateGreatCircle(from, to, step / steps));
    }
  }
  return Object.freeze(sampled.map((point) => Object.freeze([...point])));
};

const findHorizonIntersection = (from, to, project) => {
  let low = 0;
  let high = 1;
  const fromIsVisible = project(from).visible;
  for (let step = 0; step < 24; step += 1) {
    const middle = (low + high) / 2;
    const candidate = interpolateGreatCircle(from, to, middle);
    if (project(candidate).visible === fromIsVisible) low = middle;
    else high = middle;
  }
  return interpolateGreatCircle(from, to, (low + high) / 2);
};

const projectSampledLine = (points, project) => {
  if (points.length < 2) return '';

  const paths = [];
  let currentPath = '';
  let currentPointCount = 0;
  const beginPath = (point) => {
    const projected = project(point);
    currentPath = `M${formatSvgNumber(projected.x)},${formatSvgNumber(projected.y)}`;
    currentPointCount = 1;
  };
  const appendPoint = (point) => {
    const projected = project(point);
    currentPath += `L${formatSvgNumber(projected.x)},${formatSvgNumber(projected.y)}`;
    currentPointCount += 1;
  };
  const finishPath = () => {
    if (currentPointCount > 1) paths.push(currentPath);
    currentPath = '';
    currentPointCount = 0;
  };

  let previous = points[0];
  if (project(previous).visible) beginPath(previous);
  for (let index = 1; index < points.length; index += 1) {
    const next = points[index];
    const previousVisible = project(previous).visible;
    const nextVisible = project(next).visible;
    if (previousVisible && nextVisible) {
      if (!currentPath) beginPath(previous);
      appendPoint(next);
    } else if (previousVisible && !nextVisible) {
      appendPoint(findHorizonIntersection(previous, next, project));
      finishPath();
    } else if (!previousVisible && nextVisible) {
      const intersection = findHorizonIntersection(previous, next, project);
      beginPath(intersection);
      appendPoint(next);
    }
    previous = next;
  }
  finishPath();
  return paths.join('');
};

// Normalize either input winding to the same spherical interior. The integral
// is computed on sampled great-circle edges to preserve dateline continuity.
const ringOrientation = (points) => {
  let integral = 0;
  for (let index = 1; index < points.length; index += 1) {
    let delta = points[index][0] - points[index - 1][0];
    delta = ((delta + 540) % 360) - 180;
    integral += delta * (Math.sin(points[index][1] * Math.PI / 180)
      + Math.sin(points[index - 1][1] * Math.PI / 180));
  }
  return integral <= 0 ? 1 : -1;
};

const sphericalWinding = (points, position) => {
  let angle = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = toVector(points[index - 1]);
    const b = toVector(points[index]);
    const dotA = a[0] * position[0] + a[1] * position[1] + a[2] * position[2];
    const dotB = b[0] * position[0] + b[1] * position[1] + b[2] * position[2];
    const cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    angle += Math.atan2(
      position[0] * cross[0] + position[1] * cross[1] + position[2] * cross[2],
      a[0] * b[0] + a[1] * b[1] + a[2] * b[2] - dotA * dotB
    );
  }
  return angle;
};

const horizonAngle = (point, project) => Math.atan2(
  point.y - project.centerY, point.x - project.centerX
);
const positiveAngle = (angle) => (angle + Math.PI * 2) % (Math.PI * 2);

const projectSampledRing = (points, project) => {
  if (points.length < 3) return '';
  // Start in the hidden portion, so visible-first rings have a horizon entry
  // rather than a spurious interior start at which to close the clip.
  const hiddenIndex = points.findIndex((point) => !project(point).visible);
  if (hiddenIndex < 0) return `${projectSampledLine(points, project)}Z`;
  const ring = points.slice(0, -1);
  const rotated = [...ring.slice(hiddenIndex), ...ring.slice(0, hiddenIndex), ring[hiddenIndex]];
  const orientation = ringOrientation(points);
  const fragments = [];
  let current = null;
  for (let index = 1; index < rotated.length; index += 1) {
    const from = rotated[index - 1];
    const to = rotated[index];
    const fromVisible = project(from).visible;
    const toVisible = project(to).visible;
    if (!fromVisible && toVisible) {
      const entry = project(findHorizonIntersection(from, to, project));
      current = { entry, path: `M${formatSvgNumber(entry.x)},${formatSvgNumber(entry.y)}` };
    }
    if (toVisible && current) {
      const point = project(to);
      current.path += `L${formatSvgNumber(point.x)},${formatSvgNumber(point.y)}`;
    }
    if (fromVisible && !toVisible && current) {
      current.exit = project(findHorizonIntersection(from, to, project));
      current.path += `L${formatSvgNumber(current.exit.x)},${formatSvgNumber(current.exit.y)}`;
      fragments.push(current);
      current = null;
    }
  }
  if (!fragments.length) {
    // A ring enclosing the entire visible hemisphere has no visible edges.
    if (sphericalWinding(points, project.centerVector) * orientation <= Math.PI) return '';
    return `M${formatSvgNumber(project.centerX + project.radius)},${formatSvgNumber(project.centerY)}`
      + `A${project.radius},${project.radius} 0 1,1 ${formatSvgNumber(project.centerX - project.radius)},${formatSvgNumber(project.centerY)}`
      + `A${project.radius},${project.radius} 0 1,1 ${formatSvgNumber(project.centerX + project.radius)},${formatSvgNumber(project.centerY)}Z`;
  }

  const paths = [];
  const visited = new Set();
  for (const first of fragments) {
    if (visited.has(first)) continue;
    let fragment = first;
    let path = '';
    while (!visited.has(fragment)) {
      visited.add(fragment);
      const continuation = fragment.path.replace(/^M[-\d.]+,[-\d.]+/, '');
      path += path ? continuation : fragment.path;
      const exitAngle = horizonAngle(fragment.exit, project);
      const next = fragments
        .filter((candidate) => !visited.has(candidate) || candidate === first)
        .map((candidate) => ({
          candidate,
          sweep: positiveAngle(orientation > 0
            ? exitAngle - horizonAngle(candidate.entry, project)
            : horizonAngle(candidate.entry, project) - exitAngle),
        }))
        .sort((left, right) => left.sweep - right.sweep)[0];
      const { entry } = next.candidate;
      if (next.sweep > 1e-6) {
        path += `A${formatSvgNumber(project.radius)},${formatSvgNumber(project.radius)} 0 ${Number(next.sweep > Math.PI)},${Number(orientation < 0)} ${formatSvgNumber(entry.x)},${formatSvgNumber(entry.y)}`;
      }
      fragment = next.candidate;
      if (fragment === first) {
        path += 'Z';
        break;
      }
    }
    paths.push(path);
  }
  return paths.join('');
};

const sampleGeometry = (geometry) => {
  if (!geometry) return geometry;
  switch (geometry.type) {
    case 'LineString':
      return { ...geometry, coordinates: sampleLine(geometry.coordinates) };
    case 'MultiLineString':
      return { ...geometry, coordinates: geometry.coordinates.map((line) => sampleLine(line)) };
    case 'Polygon':
      return { ...geometry, coordinates: geometry.coordinates.map((ring) => sampleLine(ring, true)) };
    case 'MultiPolygon':
      return {
        ...geometry,
        coordinates: geometry.coordinates.map((polygon) => (
          polygon.map((ring) => sampleLine(ring, true))
        )),
      };
    case 'GeometryCollection':
      return { ...geometry, geometries: geometry.geometries.map(sampleGeometry) };
    default:
      return geometry;
  }
};

const geometryPath = (geometry, project) => {
  if (!geometry) return '';
  switch (geometry.type) {
    case 'LineString':
      return projectSampledLine(geometry.coordinates, project);
    case 'MultiLineString':
      return geometry.coordinates.map((line) => projectSampledLine(line, project)).join('');
    case 'Polygon':
      return geometry.coordinates.map((ring) => projectSampledRing(ring, project)).join('');
    case 'MultiPolygon':
      return geometry.coordinates.flatMap((polygon) => (
        polygon.map((ring) => projectSampledRing(ring, project))
      )).join('');
    case 'GeometryCollection':
      return geometry.geometries.map((child) => geometryPath(child, project)).join('');
    default:
      return '';
  }
};

const collectPositions = (geometry) => {
  if (!geometry) return [];
  if (geometry.type === 'Point') return [geometry.coordinates];
  if (geometry.type === 'GeometryCollection') {
    return geometry.geometries.flatMap(collectPositions);
  }
  const positions = [];
  const visit = (value) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && Number.isFinite(value[0]) && Number.isFinite(value[1])) {
      positions.push(value);
      return;
    }
    value.forEach(visit);
  };
  visit(geometry.coordinates);
  return positions;
};

const geographicCentroid = (geometry) => {
  const positions = collectPositions(geometry);
  if (!positions.length) return null;
  const vector = positions.reduce((sum, position) => {
    const [x, y, z] = toVector(position);
    return [sum[0] + x, sum[1] + y, sum[2] + z];
  }, [0, 0, 0]);
  if (Math.hypot(...vector) < 1e-8) return positions[0];
  return fromVector(vector);
};

const createSampledGraticule = () => {
  const lines = [];
  for (let longitude = -180; longitude <= 180; longitude += 30) {
    const meridian = [];
    for (let latitude = -90; latitude <= 90; latitude += 4) meridian.push([longitude, latitude]);
    lines.push(sampleLine(meridian, false, 4));
  }
  for (let latitude = -60; latitude <= 60; latitude += 30) {
    const parallel = [];
    for (let longitude = -180; longitude <= 180; longitude += 4) parallel.push([longitude, latitude]);
    lines.push(sampleLine(parallel, false, 4));
  }
  return Object.freeze(lines);
};

const createGraticulePath = (sampledLines, project) => sampledLines
  .map((line) => projectSampledLine(line, project))
  .join('');

const TacticalGlobe3D = ({
  geographyUrl,
  countryDataByIso,
  getGeoCountryInfo,
  selectedCountryCode,
  focusRequest,
  hoveredCountryCode,
  onHoverCountry,
  onSelectCountry,
  onNoDataCountryClick,
  onBackgroundClick,
  showAtmosphere = false,
  accessibleLabel = 'Globo de ancestría por país',
}) => {
  const [rotation, setRotation] = useState(INITIAL_ROTATION);
  const [viewport, setViewport] = useState({ width: GLOBE_WIDTH, height: GLOBE_HEIGHT });
  const [hasRevealed, setHasRevealed] = useState(false);
  const [isKeyboardFocusWithinGlobe, setIsKeyboardFocusWithinGlobe] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isFocusTransitioning, setIsFocusTransitioning] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(readReducedMotionPreference);
  const [isDocumentVisible, setIsDocumentVisible] = useState(() => (
    typeof document === 'undefined' || document.visibilityState !== 'hidden'
  ));
  const [isGlobeIntersecting, setIsGlobeIntersecting] = useState(true);
  const [focusedCountryCode, setFocusedCountryCode] = useState(null);
  const [topology, setTopology] = useState(null);
  const globeRef = useRef(null);
  const dragRef = useRef(null);
  const rotationRef = useRef(rotation);
  const getGeoCountryInfoRef = useRef(getGeoCountryInfo);
  const prefersReducedMotionRef = useRef(prefersReducedMotion);
  const lastFocusRequestKeyRef = useRef(null);
  const activeFocusRequestKeyRef = useRef(null);
  const focusAnimationFrameRef = useRef(null);
  const rotationFrameRef = useRef(null);
  const dragUpdateFrameRef = useRef(null);
  const pendingDragRotationRef = useRef(null);
  const lastRotationTimestampRef = useRef(null);
  const suppressClickRef = useRef(false);
  const suppressBackgroundClickRef = useRef(false);
  rotationRef.current = rotation;
  getGeoCountryInfoRef.current = getGeoCountryInfo;
  prefersReducedMotionRef.current = prefersReducedMotion;
  const isSelectedCountryPositive = hasPositiveAncestry(
    countryDataByIso?.get(selectedCountryCode)
  );
  const isRotationPaused = prefersReducedMotion
    || !isDocumentVisible
    || !isGlobeIntersecting
    || isSelectedCountryPositive
    || isKeyboardFocusWithinGlobe
    || isDragging
    || isFocusTransitioning;
  const isRotationPausedRef = useRef(isRotationPaused);
  isRotationPausedRef.current = isRotationPaused;

  const updateRotation = useCallback((elapsedMs) => {
    const rotationStep = IDLE_ROTATION_DEGREES_PER_SECOND * elapsedMs / 1000;
    setRotation(([longitude, latitude, roll]) => [
      (longitude + rotationStep) % 360,
      latitude,
      roll,
    ]);
  }, []);
  const startIdleRotation = useCallback(() => {
    if (isRotationPausedRef.current || rotationFrameRef.current !== null) return;

    const rotateOnFrame = (timestamp) => {
      rotationFrameRef.current = null;
      if (isRotationPausedRef.current) {
        lastRotationTimestampRef.current = null;
        return;
      }

      const previousTimestamp = lastRotationTimestampRef.current;
      if (previousTimestamp === null) {
        lastRotationTimestampRef.current = timestamp;
      } else {
        const elapsedMs = Math.min(
          Math.max(timestamp - previousTimestamp, 0),
          MAX_ROTATION_ELAPSED_MS
        );
        if (elapsedMs >= IDLE_ROTATION_FRAME_INTERVAL_MS) {
          updateRotation(elapsedMs);
          lastRotationTimestampRef.current = timestamp;
        }
      }

      if (!isRotationPausedRef.current && rotationFrameRef.current === null) {
        rotationFrameRef.current = window.requestAnimationFrame(rotateOnFrame);
      }
    };

    rotationFrameRef.current = window.requestAnimationFrame(rotateOnFrame);
  }, [updateRotation]);
  const stopIdleRotation = useCallback(() => {
    if (rotationFrameRef.current !== null) {
      window.cancelAnimationFrame(rotationFrameRef.current);
      rotationFrameRef.current = null;
    }
    lastRotationTimestampRef.current = null;
  }, []);

  const geographies = useMemo(() => decodeTopology(topology), [topology]);
  const radius = useMemo(() => (
    Math.round(Math.min(
      getGlobeRadius(viewport, showAtmosphere) * INITIAL_GLOBE_SCALE,
      Math.min(viewport.width, viewport.height) / 2 - (showAtmosphere ? 7.5 : 0.55)
    ) * 100) / 100
  ), [viewport, showAtmosphere]);
  const project = useMemo(() => createOrthographicProjector(
    rotation,
    viewport.width,
    viewport.height,
    radius
  ), [rotation, viewport, radius]);
  const stars = useMemo(() => createStableStars(viewport.width, viewport.height, radius), [
    viewport,
    radius,
  ]);
  const sampledGraticule = useMemo(createSampledGraticule, []);
  const graticulePath = useMemo(() => createGraticulePath(sampledGraticule, project), [
    sampledGraticule,
    project,
  ]);
  const geographiesWithCentroids = useMemo(() => geographies.map((geography) => ({
    ...geography,
    centroid: geographicCentroid(geography.geometry),
    sampledGeometry: sampleGeometry(geography.geometry),
  })), [geographies]);
  const projectedGeographies = useMemo(() => geographiesWithCentroids.map((geography) => ({
    ...geography,
    path: geometryPath(geography.sampledGeometry, project),
  })), [geographiesWithCentroids, project]);

  useEffect(() => {
    const countryCode = focusRequest?.countryCode;
    const requestId = focusRequest?.requestId;
    if (typeof countryCode !== 'string' || !countryCode || requestId === undefined || requestId === null) {
      setIsFocusTransitioning(false);
      return undefined;
    }

    const requestKey = `${String(requestId)}:${countryCode}`;
    if (lastFocusRequestKeyRef.current === requestKey) return undefined;

    const geography = geographiesWithCentroids.find((candidate) => (
      candidate.centroid && getGeoCountryInfoRef.current?.(candidate)?.code === countryCode
    ));
    if (!geography) {
      setIsFocusTransitioning(false);
      return undefined;
    }

    if (focusAnimationFrameRef.current !== null) {
      window.cancelAnimationFrame(focusAnimationFrameRef.current);
      focusAnimationFrameRef.current = null;
    }

    const startRotation = rotationRef.current;
    const longitudeDelta = (((geography.centroid[0] - startRotation[0] + 180) % 360) + 360) % 360 - 180;
    const targetRotation = [
      startRotation[0] + longitudeDelta,
      geography.centroid[1],
      startRotation[2],
    ];
    if (prefersReducedMotionRef.current
      || (Math.abs(longitudeDelta) < 1e-6
        && Math.abs(targetRotation[1] - startRotation[1]) < 1e-6)) {
      lastFocusRequestKeyRef.current = requestKey;
      rotationRef.current = targetRotation;
      setRotation(targetRotation);
      setIsFocusTransitioning(false);
      return undefined;
    }

    stopIdleRotation();
    activeFocusRequestKeyRef.current = requestKey;
    setIsFocusTransitioning(true);
    let startTimestamp = null;
    const animateFocus = (timestamp) => {
      focusAnimationFrameRef.current = null;
      if (prefersReducedMotionRef.current) {
        lastFocusRequestKeyRef.current = requestKey;
        activeFocusRequestKeyRef.current = null;
        rotationRef.current = targetRotation;
        setRotation(targetRotation);
        setIsFocusTransitioning(false);
        return;
      }

      if (startTimestamp === null) startTimestamp = timestamp;
      const progress = Math.min(1, (timestamp - startTimestamp) / COUNTRY_FOCUS_TRANSITION_MS);
      const easedProgress = 1 - (1 - progress) ** 3;
      const nextRotation = [
        startRotation[0] + longitudeDelta * easedProgress,
        startRotation[1] + (targetRotation[1] - startRotation[1]) * easedProgress,
        startRotation[2],
      ];
      rotationRef.current = nextRotation;
      setRotation(nextRotation);

      if (progress >= 1) {
        lastFocusRequestKeyRef.current = requestKey;
        activeFocusRequestKeyRef.current = null;
        rotationRef.current = targetRotation;
        setRotation(targetRotation);
        setIsFocusTransitioning(false);
        return;
      }
      focusAnimationFrameRef.current = window.requestAnimationFrame(animateFocus);
    };

    focusAnimationFrameRef.current = window.requestAnimationFrame(animateFocus);
    return () => {
      if (focusAnimationFrameRef.current !== null) {
        window.cancelAnimationFrame(focusAnimationFrameRef.current);
        focusAnimationFrameRef.current = null;
      }
      if (activeFocusRequestKeyRef.current === requestKey) {
        activeFocusRequestKeyRef.current = null;
      }
    };
  }, [
    focusRequest?.countryCode,
    focusRequest?.requestId,
    geographiesWithCentroids,
    stopIdleRotation,
  ]);

  useEffect(() => {
    const controller = new AbortController();
    let isCurrent = true;
    setTopology(null);
    if (!geographyUrl) {
      return () => {
        isCurrent = false;
        controller.abort();
      };
    }
    fetch(geographyUrl, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Unable to load globe geography (${response.status}).`);
        const responseText = await readBoundedResponseText(response);
        const loadedTopology = JSON.parse(responseText);
        if (!isValidTopology(loadedTopology)) throw new Error('Invalid globe geography topology.');
        return loadedTopology;
      })
      .then((loadedTopology) => {
        if (isCurrent) setTopology(loadedTopology);
      })
      .catch(() => {
        if (isCurrent) setTopology(null);
      });
    return () => {
      isCurrent = false;
      controller.abort();
    };
  }, [geographyUrl]);

  useEffect(() => {
    const measureViewport = () => {
      const bounds = globeRef.current?.getBoundingClientRect();
      const width = bounds?.width || globeRef.current?.clientWidth;
      const height = bounds?.height || globeRef.current?.clientHeight;
      if (!width || !height) return;
      setViewport((current) => (
        current.width === width && current.height === height ? current : { width, height }
      ));
    };
    measureViewport();
    window.addEventListener('resize', measureViewport);
    const observer = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(measureViewport);
    if (observer && globeRef.current) observer.observe(globeRef.current);
    return () => {
      window.removeEventListener('resize', measureViewport);
      observer?.disconnect();
    };
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mediaQuery) return undefined;

    const updatePreference = (event) => setPrefersReducedMotion(event.matches);
    mediaQuery.addEventListener?.('change', updatePreference);
    return () => mediaQuery.removeEventListener?.('change', updatePreference);
  }, []);

  useEffect(() => {
    const updateDocumentVisibility = () => {
      setIsDocumentVisible(document.visibilityState !== 'hidden');
    };
    document.addEventListener('visibilitychange', updateDocumentVisibility);
    updateDocumentVisibility();
    return () => document.removeEventListener('visibilitychange', updateDocumentVisibility);
  }, []);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined' || !globeRef.current) return undefined;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry) setIsGlobeIntersecting(entry.isIntersecting);
    });
    observer.observe(globeRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const revealTimeoutId = window.setTimeout(() => {
      setHasRevealed(true);
      startIdleRotation();
    }, ENTRY_REVEAL_MS);
    return () => {
      window.clearTimeout(revealTimeoutId);
      stopIdleRotation();
      if (dragUpdateFrameRef.current !== null) {
        window.cancelAnimationFrame(dragUpdateFrameRef.current);
        dragUpdateFrameRef.current = null;
      }
      pendingDragRotationRef.current = null;
    };
  }, [startIdleRotation, stopIdleRotation]);

  useEffect(() => {
    if (!hasRevealed || isRotationPaused) {
      stopIdleRotation();
      return;
    }
    startIdleRotation();
  }, [hasRevealed, isRotationPaused, startIdleRotation, stopIdleRotation]);

  const flushPendingDragRotation = useCallback(() => {
    const pendingRotation = pendingDragRotationRef.current;
    if (dragUpdateFrameRef.current !== null) {
      window.cancelAnimationFrame(dragUpdateFrameRef.current);
      dragUpdateFrameRef.current = null;
    }
    pendingDragRotationRef.current = null;
    if (pendingRotation) setRotation(pendingRotation);
  }, []);

  const handlePointerDown = useCallback((event) => {
    event.stopPropagation();
    if (focusAnimationFrameRef.current !== null) {
      window.cancelAnimationFrame(focusAnimationFrameRef.current);
      focusAnimationFrameRef.current = null;
      lastFocusRequestKeyRef.current = activeFocusRequestKeyRef.current;
      activeFocusRequestKeyRef.current = null;
      setIsFocusTransitioning(false);
    }
    setIsKeyboardFocusWithinGlobe(false);
    if (event.button !== undefined && event.button !== 0 && event.pointerType !== 'touch') return;
    setIsDragging(true);
    suppressClickRef.current = false;
    suppressBackgroundClickRef.current = false;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startRotation: rotation,
      moved: false,
    };
  }, [rotation]);

  const handlePointerMove = useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;
    if (!drag.moved && Math.abs(deltaX) + Math.abs(deltaY) > 3) {
      drag.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    if (!drag.moved) return;

    pendingDragRotationRef.current = [
      drag.startRotation[0] - deltaX * 0.6,
      Math.max(-85, Math.min(85, drag.startRotation[1] + deltaY * 0.6)),
      drag.startRotation[2],
    ];
    if (dragUpdateFrameRef.current === null) {
      dragUpdateFrameRef.current = window.requestAnimationFrame(() => {
        dragUpdateFrameRef.current = null;
        const pendingRotation = pendingDragRotationRef.current;
        pendingDragRotationRef.current = null;
        if (pendingRotation) setRotation(pendingRotation);
      });
    }
  }, []);

  const handlePointerUp = useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    suppressClickRef.current = drag.moved;
    suppressBackgroundClickRef.current = drag.moved;
    flushPendingDragRotation();
    dragRef.current = null;
    setIsDragging(false);
  }, [flushPendingDragRotation]);

  const handlePointerCancel = useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    flushPendingDragRotation();
    dragRef.current = null;
    setIsDragging(false);
    suppressClickRef.current = false;
    suppressBackgroundClickRef.current = false;
  }, [flushPendingDragRotation]);

  const handleMapClickCapture = useCallback((event) => {
    if (!suppressClickRef.current) {
      suppressBackgroundClickRef.current = false;
      return;
    }
    suppressClickRef.current = false;

    const isPointerClick = event.detail > 0 || Boolean(event.nativeEvent.pointerType);
    const clickedCountry = event.target.closest?.('.ancestria-map-country');
    if (isPointerClick && clickedCountry) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, []);

  const handleBackgroundClick = useCallback((event) => {
    if (suppressBackgroundClickRef.current) {
      event.stopPropagation();
      suppressBackgroundClickRef.current = false;
      return;
    }
    onBackgroundClick?.(event);
  }, [onBackgroundClick]);

  const handleCountrySelect = useCallback((countryInfo, countryData, event) => {
    event.stopPropagation();
    if (!hasPositiveAncestry(countryData)) {
      onNoDataCountryClick?.(countryInfo, event);
      return;
    }
    onSelectCountry?.(countryData, countryInfo, event);
  }, [onNoDataCountryClick, onSelectCountry]);

  const renderCountry = (geography) => {
    if (!geography.path) return null;
    const countryInfo = getGeoCountryInfo?.(geography);
    if (!countryInfo) return null;

    const countryData = countryDataByIso?.get(countryInfo.code) || null;
    const isSelectable = hasPositiveAncestry(countryData);
    const isSelected = isSelectable && countryInfo.code === selectedCountryCode;
    const isHovered = countryInfo.code === hoveredCountryCode
      || countryInfo.code === focusedCountryCode;
    const stroke = isSelected ? '#01579B' : isHovered ? '#5B636A' : DEFAULT_COUNTRY_STROKE;
    const strokeWidth = isSelected ? 1.8 : isHovered ? 1.4 : 0.75;
    const countryName = countryData?.name || countryInfo.name || geography.properties?.name || 'País';
    const percentageLabel = formatPercentage(countryData?.percentage);
    const accessibleName = [countryName, percentageLabel, 'seleccionar país'].filter(Boolean).join(', ');

    const selectFromKeyboard = (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      handleCountrySelect(countryInfo, countryData, event);
    };

    return (
      <path
        key={geography.id ?? geography.properties?.name}
        d={geography.path}
        data-geography-id={geography.id}
        className="ancestria-map-country"
        fill={hasPositiveAncestry(countryData)
          ? POSITIVE_COUNTRY_FILL
          : NEUTRAL_COUNTRY_FILL}
        stroke={stroke}
        strokeWidth={strokeWidth}
        fillRule="evenodd"
        role={isSelectable ? 'button' : undefined}
        tabIndex={isSelectable ? 0 : undefined}
        aria-label={isSelectable ? accessibleName : undefined}
        aria-pressed={isSelectable ? isSelected : undefined}
        onClick={(event) => handleCountrySelect(countryInfo, countryData, event)}
        onKeyDown={isSelectable ? selectFromKeyboard : undefined}
        onFocus={() => {
          if (isSelectable) {
            setFocusedCountryCode(countryInfo.code);
            onHoverCountry?.(countryInfo.code);
          }
        }}
        onBlur={() => {
          setFocusedCountryCode(null);
          onHoverCountry?.(null);
        }}
        style={{ cursor: isSelectable ? 'pointer' : 'default', transition: 'fill 140ms ease, filter 140ms ease, stroke 140ms ease' }}
      />
    );
  };

  const renderAnnotations = () => {
    const placedLabelBounds = [];
    const { width, height } = project;
    return (
      <g
        className="tactical-globe__annotations"
        data-globe-annotations="true"
        aria-hidden="true"
        pointerEvents="none"
      >
        {projectedGeographies.map((geography) => {
          const countryInfo = getGeoCountryInfo?.(geography);
          if (!countryInfo || !geography.centroid) return null;

          const countryData = countryDataByIso?.get(countryInfo.code);
          const countryHasPositiveAncestry = hasPositiveAncestry(countryData);
          if (!countryHasPositiveAncestry) return null;

          const point = project(geography.centroid);
          if (!point.visible || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
          const { x, y } = point;
          const preferredSide = x > width * 0.8 ? -1 : 1;
          const countryName = countryData?.name
            || countryInfo.name
            || geography.properties?.name
            || 'País';
          let labelPlacement = null;

          if (countryHasPositiveAncestry) {
            const textWidth = Array.from(countryName).length * LABEL_FONT_SIZE * 0.62;
            const verticalOffsets = [3, -15, 21, -33, 39, -51, 57, -69, 75];
            const candidates = verticalOffsets.flatMap((offsetY) => (
              [preferredSide, -preferredSide].map((side) => ({
                x: side * 11,
                y: offsetY,
                textAnchor: side < 0 ? 'end' : 'start',
              }))
            ));
            const evaluatedCandidates = candidates.map((candidate) => {
              const textX = x + candidate.x;
              const baselineY = y + candidate.y;
              const bounds = {
                left: (candidate.textAnchor === 'end' ? textX - textWidth : textX)
                  - LABEL_STROKE_ALLOWANCE,
                right: (candidate.textAnchor === 'end' ? textX : textX + textWidth)
                  + LABEL_STROKE_ALLOWANCE,
                top: baselineY - LABEL_FONT_SIZE * 0.85 - LABEL_STROKE_ALLOWANCE,
                bottom: baselineY + LABEL_FONT_SIZE * 0.2 + LABEL_STROKE_ALLOWANCE,
              };
              const isInsideViewport = bounds.left >= 0
                && bounds.right <= width
                && bounds.top >= 0
                && bounds.bottom <= height;
              const collides = placedLabelBounds.some((placed) => (
                bounds.left < placed.right + LABEL_COLLISION_GAP
                && bounds.right + LABEL_COLLISION_GAP > placed.left
                && bounds.top < placed.bottom + LABEL_COLLISION_GAP
                && bounds.bottom + LABEL_COLLISION_GAP > placed.top
              ));
              return { ...candidate, bounds, isInsideViewport, collides };
            });
            labelPlacement = evaluatedCandidates.find(({ isInsideViewport, collides }) => (
              isInsideViewport && !collides
            )) || evaluatedCandidates.find(({ collides }) => !collides) || evaluatedCandidates[0];
            placedLabelBounds.push(labelPlacement.bounds);
          }

          return (
            <g key={`annotation-${geography.id ?? countryInfo.code}`} transform={`translate(${x}, ${y})`}>
              {countryHasPositiveAncestry && (
                <g className="tactical-globe__pin" data-globe-pin={countryInfo.code}>
                  <circle
                    className="tactical-globe__pin-pulse"
                    r="7"
                    fill="#0b77cc"
                  />
                  <circle r="10.5" fill="rgba(229,62,62,0.14)" />
                  <circle r="5" fill={LOCATOR_PIN_COLOR} />
                  <circle cx="-1.75" cy="-1.75" r="1.75" fill="rgba(255,255,255,0.55)" />
                </g>
              )}
              {countryHasPositiveAncestry && (
                <text
                  className="tactical-globe__label"
                  data-globe-label={countryInfo.code}
                  x={labelPlacement.x}
                  y={labelPlacement.y}
                  textAnchor={labelPlacement.textAnchor}
                >
                  {countryName}
                </text>
              )}
            </g>
          );
        })}
      </g>
    );
  };

  return (
    <div
      ref={globeRef}
      className="tactical-globe"
      role="region"
      aria-label={accessibleLabel}
      onFocusCapture={(event) => {
        setIsKeyboardFocusWithinGlobe(
          Boolean(event.target.matches?.(':focus-visible'))
        );
      }}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsKeyboardFocusWithinGlobe(false);
        }
      }}
    >
      <svg
        className="tactical-globe__svg"
        viewBox={`0 0 ${viewport.width} ${viewport.height}`}
        width={viewport.width}
        height={viewport.height}
        preserveAspectRatio="xMidYMid meet"
        data-projection="geoOrthographic"
        data-rotation={JSON.stringify(rotation)}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onLostPointerCapture={handlePointerCancel}
        onClickCapture={handleMapClickCapture}
        onClick={handleBackgroundClick}
      >
        <defs>
          <clipPath id="tactical-globe-sphere-clip">
            <circle cx={project.centerX} cy={project.centerY} r={radius} />
          </clipPath>
          <linearGradient id="tactical-globe-linear-shading" x1="12%" y1="10%" x2="88%" y2="90%">
            <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.22" />
            <stop offset="48%" stopColor="#FFFFFF" stopOpacity="0" />
            <stop offset="100%" stopColor="#1A1A20" stopOpacity="0.46" />
          </linearGradient>
          <radialGradient id="tactical-globe-edge-shading" cx="42%" cy="38%" r="68%">
            <stop offset="58%" stopColor="#1A1A20" stopOpacity="0" />
            <stop offset="100%" stopColor="#1A1A20" stopOpacity="0.48" />
          </radialGradient>
        </defs>
        <g
          className="tactical-globe__world"
          style={{ animation: prefersReducedMotion ? 'none' : undefined }}
        >
          <g data-globe-stars="true" aria-hidden="true">
            {stars.map((star, index) => (
              <circle
                key={`star-${index}`}
                data-globe-star="true"
                cx={star.x}
                cy={star.y}
                r={star.size}
                fill="#FFFFFF"
                opacity={star.opacity}
              />
            ))}
          </g>
          <circle
            data-globe-sphere="true"
            cx={project.centerX}
            cy={project.centerY}
            r={radius}
            fill={OCEAN_COLOR}
            stroke="#4D555D"
            strokeWidth="1.1"
            aria-hidden="true"
          />
          <circle
            cx={project.centerX}
            cy={project.centerY}
            r={radius}
            fill="url(#tactical-globe-linear-shading)"
            pointerEvents="none"
            aria-hidden="true"
          />
          <circle
            cx={project.centerX}
            cy={project.centerY}
            r={radius}
            fill="url(#tactical-globe-edge-shading)"
            pointerEvents="none"
            aria-hidden="true"
          />
          <path
            data-globe-graticule="true"
            d={graticulePath}
            clipPath="url(#tactical-globe-sphere-clip)"
            stroke="#FFFFFF"
            strokeWidth="0.55"
            opacity="0.48"
            fill="none"
            pointerEvents="stroke"
            aria-hidden="true"
          />
          <g clipPath="url(#tactical-globe-sphere-clip)">
            {projectedGeographies.map(renderCountry)}
          </g>
          {renderAnnotations()}
          {showAtmosphere && (
            <circle
              data-globe-atmosphere="true"
              cx={project.centerX}
              cy={project.centerY}
              r={radius + 5}
              fill="none"
              stroke="#B6D8E4"
              strokeOpacity="0.32"
              strokeWidth="5"
              pointerEvents="none"
              aria-hidden="true"
            />
          )}
        </g>
      </svg>
    </div>
  );
};

export default TacticalGlobe3D;
