import { useCallback, useEffect, useRef, useState } from 'react';
import { getGenomicsServices, getGenomicsServiceResults } from '../services/genomicsService';

const clearedState = (status = 'loading', error = null) => ({
  status, service: null, data: null, error,
});
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
class InvalidGenomicsData extends Error {}

const purchaseKey = (value) => {
  if (typeof value !== 'string') throw new InvalidGenomicsData();
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|\+00:00)$/.exec(value);
  if (!match || match[1].startsWith('0000-')) throw new InvalidGenomicsData();
  const date = new Date(`${match[1]}Z`);
  // Date parsing alone normalizes invalid calendar dates (e.g. February 30).
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 19) !== match[1]) {
    throw new InvalidGenomicsData();
  }
  // UTC calendar order is lexical. Keep the fraction, not Date's millisecond truncation;
  // remove trailing zeros so .123 and .123000 are the same instant.
  return `${match[1]}.${(match[2] || '').replace(/0+$/, '')}`;
};

const selectLatestService = (data) => {
  if (!isObject(data) || !Array.isArray(data.services)) throw new InvalidGenomicsData();
  let selected = null;
  let latestKey = '';
  for (const service of data.services) {
    if (!isObject(service) || typeof service.service_request_id !== 'string'
      || !service.service_request_id.trim()) throw new InvalidGenomicsData();
    const key = purchaseKey(service.purchased_at);
    // Validate every entry, including older ones. Exact ties keep backend canonical order.
    if (key > latestKey) {
      selected = service;
      latestKey = key;
    }
  }
  return selected;
};

const validateResults = (data, service) => {
  if (!isObject(data) || data.service_request_id !== service.service_request_id
    || !Array.isArray(data.results)) throw new InvalidGenomicsData();
};
const responseError = (response, resource) => ({
  kind: response.status === 0 ? 'connection' : 'http',
  resource,
  status: response.status,
});
const failureState = (error) => clearedState(
  error.status === 401 || error.status === 403 ? 'permission' : 'error', error,
);

/**
 * status: loading | ready | empty | permission | error; loading is also a boolean.
 * service is the selected list entry; data is the untouched results envelope,
 * including synthetic/non-clinical disclosure. An empty list has neither.
 * error: { kind: http | connection | invalid_data, resource: services | results, status }.
 * retry clears all previous data and reloads the owner-scoped list; no older/legacy fallback.
 */
export const useLatestGenomicsResults = () => {
  const [state, setState] = useState(clearedState);
  const mounted = useRef(false);
  const generation = useRef(0);

  const retry = useCallback(() => {
    if (!mounted.current) return;
    const requestGeneration = ++generation.current;
    const isCurrent = () => mounted.current && generation.current === requestGeneration;
    setState(clearedState());

    const load = async () => {
      let resource = 'services';
      let status = 0;
      try {
        const list = await getGenomicsServices();
        if (!isCurrent()) return;
        if (!list.ok) {
          setState(failureState(responseError(list, resource)));
          return;
        }
        status = list.status;
        const service = selectLatestService(list.data);
        if (!service) {
          setState(clearedState('empty'));
          return;
        }

        resource = 'results';
        status = 0;
        const response = await getGenomicsServiceResults(service.service_request_id);
        if (!isCurrent()) return;
        if (!response.ok) {
          setState(failureState(responseError(response, resource)));
          return;
        }
        status = response.status;
        validateResults(response.data, service);
        setState({
          status: response.data.results.length ? 'ready' : 'empty',
          service,
          data: response.data,
          error: null,
        });
      } catch (error) {
        if (!isCurrent()) return;
        setState(failureState({
          kind: error instanceof InvalidGenomicsData ? 'invalid_data' : 'connection',
          resource,
          status,
        }));
      }
    };
    void load();
  }, []);

  useEffect(() => {
    mounted.current = true;
    retry();
    return () => { mounted.current = false; };
  }, [retry]);

  return { ...state, loading: state.status === 'loading', retry };
};
