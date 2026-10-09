import { useCallback, useEffect, useRef, useState } from 'react';
import { API_ENDPOINTS, apiRequest } from '../config/api';

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const stateFor = (status, data = null, error = null) => ({ status, data, error });

/**
 * Newest COMPLETED service results of the signed-in client.
 * status: loading | ready | empty | permission | error. data: { disclaimer, sample_code, modules, ... }.
 * The backend answers 404 when the client has no viewable results.
 */
export const useLatestGenomicsResults = () => {
  const [state, setState] = useState(() => stateFor('loading'));
  const mounted = useRef(false);
  const generation = useRef(0);

  const retry = useCallback(() => {
    if (!mounted.current) return;
    const requestGeneration = ++generation.current;
    setState(stateFor('loading'));

    void apiRequest(API_ENDPOINTS.GENOMICS_RESULTS, { method: 'GET' }).then((response) => {
      if (!mounted.current || generation.current !== requestGeneration) return;
      const { ok, status, data } = response;
      if (ok && isObject(data) && isObject(data.modules)) setState(stateFor('ready', data));
      else if (status === 404) setState(stateFor('empty'));
      else if (status === 401 || status === 403) setState(stateFor('permission', null, { status }));
      else setState(stateFor('error', null, { status, kind: ok ? 'invalid_data' : status ? 'http' : 'connection' }));
    });
  }, []);

  useEffect(() => {
    mounted.current = true;
    retry();
    return () => { mounted.current = false; };
  }, [retry]);

  return { ...state, loading: state.status === 'loading', retry };
};

export const moduleRows = (results, module) => {
  const rows = results.data?.modules?.[module];
  return Array.isArray(rows) ? rows : [];
};
