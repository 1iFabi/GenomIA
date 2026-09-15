import * as topojson from 'topojson-client';

const getTopologyObject = (topology) => {
  if (!topology?.objects) return null;

  return topology.objects.countries || Object.values(topology.objects)[0] || null;
};

export const topologyToFeatureCollection = (topology) => {
  const topologyObject = getTopologyObject(topology);

  if (!topologyObject) {
    throw new Error('The map topology does not contain a geographic object.');
  }

  const geojson = topojson.feature(topology, topologyObject);

  if (geojson.type === 'FeatureCollection') {
    return geojson;
  }

  return {
    type: 'FeatureCollection',
    features: [geojson],
  };
};

export const fetchChoroplethGeoJson = async (url, signal) => {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    throw new Error(`Unable to load map geometry (${response.status}).`);
  }

  const topology = await response.json();
  return topologyToFeatureCollection(topology);
};
