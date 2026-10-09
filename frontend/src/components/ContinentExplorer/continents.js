export const CONTINENT_LABELS = {
  'South America': 'Sudamérica',
  'North America': 'Norteamérica',
  Europe: 'Europa',
  Africa: 'África',
  Asia: 'Asia',
  Oceania: 'Oceanía',
};

// Lon/lat frame for each silhouette. Neighbors inside the frame are drawn faintly so the shape reads in context.
const FRAMES = {
  'South America': [-83, -56, -33, 13],
  'North America': [-170, 6, -50, 74],
  Europe: [-25, 34, 45, 71],
  Africa: [-19, -36, 53, 38],
  Asia: [25, -11, 148, 62],
  Oceania: [110, -48, 180, 2],
};

// Groups ancestry rows by the geographic continent of each reference country (not by genetic group).
export const groupByContinent = (rows, continentOf) => {
  const byKey = new Map();
  for (const row of rows) {
    const key = row.country_code && continentOf(row.country_code);
    if (!key) continue;
    const entry = byKey.get(key) || { key, label: CONTINENT_LABELS[key] || key, proportion: 0, rows: [] };
    entry.proportion += row.proportion;
    entry.rows.push(row);
    byKey.set(key, entry);
  }
  return [...byKey.values()]
    .map((entry) => ({ ...entry, rows: entry.rows.sort((a, b) => b.proportion - a.proportion) }))
    .sort((a, b) => b.proportion - a.proportion);
};

const ringsOf = (geometry) => {
  if (geometry?.type === 'Polygon') return geometry.coordinates;
  if (geometry?.type === 'MultiPolygon') return geometry.coordinates.flat();
  return [];
};

// Rings that cross the antimeridian (Russia, Antarctica) jump from 180 to -180; keep longitude continuous
// so they don't draw a stripe across the whole frame.
const unwrap = (ring) => {
  let offset = 0;
  return ring.map(([lon, lat], index) => {
    if (index) {
      const previous = ring[index - 1][0];
      if (lon - previous > 180) offset -= 360;
      else if (previous - lon > 180) offset += 360;
    }
    return [lon + offset, lat];
  });
};

// Equirectangular, with longitude squeezed by cos(mid-latitude) so high-latitude continents keep their shape.
const pathFor = (geometries, squeeze) => geometries.flatMap((geometry) => ringsOf(geometry).map((ring) => (
  `M${unwrap(ring).map(([lon, lat]) => `${(lon * squeeze).toFixed(1)},${(-lat).toFixed(1)}`).join('L')}Z`
))).join('');

export const buildContinentShapes = (geographies, getInfo, continents) => {
  if (!geographies.length) return {};
  const info = geographies.map((geography) => ({ geography, info: getInfo(geography) }));
  const shapes = {};
  for (const continent of continents) {
    const frame = FRAMES[continent.key];
    if (!frame) continue;
    const [west, south, east, north] = frame;
    const squeeze = Math.cos((((south + north) / 2) * Math.PI) / 180);
    const ancestry = new Set(continent.rows.map((row) => row.country_code));
    const layers = { context: [], land: [], ancestry: [] };
    for (const { geography, info: country } of info) {
      if (country?.continent !== continent.key) layers.context.push(geography.geometry);
      else if (ancestry.has(country.code)) layers.ancestry.push(geography.geometry);
      else layers.land.push(geography.geometry);
    }
    shapes[continent.key] = {
      viewBox: `${(west * squeeze).toFixed(1)} ${-north} ${((east - west) * squeeze).toFixed(1)} ${north - south}`,
      context: pathFor(layers.context, squeeze),
      land: pathFor(layers.land, squeeze),
      ancestry: pathFor(layers.ancestry, squeeze),
    };
  }
  return shapes;
};
