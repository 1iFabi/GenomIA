import React, { act, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { moduleRows, useLatestGenomicsResults } from './useLatestGenomicsResults';

const results = (modules = { traits: [{ trait: 'cafeina', label: 'Cafeína', result: 'Rápido' }] }) => ({
  service_request_id: 'latest', sample_code: 'SEED-1', disclaimer: 'Resultados de desarrollo.', modules,
});
const reply = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
});
const deferred = () => {
  let resolve;
  const promise = new Promise((res) => { resolve = res; });
  return { promise, resolve };
};

let root;
let container;
let state;

const mount = async (strict = false) => {
  const Probe = () => {
    state = useLatestGenomicsResults();
    return null;
  };
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(strict ? <StrictMode><Probe /></StrictMode> : <Probe />));
};
const resultCalls = () => fetch.mock.calls.filter(([url]) => url === '/api/genoma/v1/results/');

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', vi.fn());
  state = null;
});
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container?.remove();
  container = null;
  vi.unstubAllGlobals();
});

describe('useLatestGenomicsResults', () => {
  it('loads the client results with one authenticated GET', async () => {
    const data = results();
    fetch.mockResolvedValue(reply(data));
    await mount();
    expect(state).toMatchObject({ status: 'ready', loading: false, data, error: null });
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/genoma/v1/results/', {
      method: 'GET', credentials: 'include', headers: {},
    });
  });

  it('starts in loading without data', async () => {
    fetch.mockReturnValue(new Promise(() => {}));
    await mount();
    expect(state).toMatchObject({ status: 'loading', loading: true, data: null, error: null });
  });

  it('maps 404 to empty', async () => {
    fetch.mockResolvedValue(reply({ error: 'No hay resultados disponibles' }, 404));
    await mount();
    expect(state).toMatchObject({ status: 'empty', data: null, error: null });
  });

  it.each([401, 403])('maps HTTP %s to permission', async (status) => {
    fetch.mockResolvedValue(reply({ detail: 'denied' }, status));
    await mount();
    expect(state).toMatchObject({ status: 'permission', data: null, error: { status } });
  });

  it.each([
    ['http', () => reply({ error: 'boom' }, 500), { kind: 'http', status: 500 }],
    ['connection', () => Promise.reject(new TypeError('offline')), { kind: 'connection', status: 0 }],
    ['invalid_data', () => reply({ results: [] }), { kind: 'invalid_data', status: 200 }],
  ])('reports %s errors without data', async (_kind, response, error) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    fetch.mockImplementation(response);
    await mount();
    expect(state).toMatchObject({ status: 'error', data: null, error });
  });

  it('clears data on retry and ignores a superseded response', async () => {
    fetch.mockResolvedValueOnce(reply(results()));
    await mount();
    const stale = deferred();
    const fresh = deferred();
    fetch.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);
    await act(async () => state.retry());
    expect(state).toMatchObject({ status: 'loading', data: null });
    await act(async () => state.retry());
    const freshData = results({ traits: [] });
    await act(async () => fresh.resolve(reply(freshData)));
    await act(async () => stale.resolve(reply(results())));
    expect(state).toMatchObject({ status: 'ready', data: freshData });
  });

  it('settles after StrictMode replays the effect', async () => {
    fetch.mockImplementation(async () => reply(results()));
    await mount(true);
    expect(state.status).toBe('ready');
    expect(resultCalls().length).toBeGreaterThanOrEqual(1);
  });

  it('does not update after unmount', async () => {
    const pending = deferred();
    fetch.mockReturnValue(pending.promise);
    await mount();
    const last = state;
    await act(async () => root.unmount());
    root = null;
    await act(async () => pending.resolve(reply(results())));
    expect(state).toBe(last);
  });
});

describe('moduleRows', () => {
  it('returns the module rows or an empty list', () => {
    const rows = [{ trait: 'cafeina' }];
    expect(moduleRows({ data: { modules: { traits: rows } } }, 'traits')).toBe(rows);
    expect(moduleRows({ data: { modules: {} } }, 'traits')).toEqual([]);
    expect(moduleRows({ data: { modules: { traits: 'bad' } } }, 'traits')).toEqual([]);
    expect(moduleRows({ data: null }, 'traits')).toEqual([]);
  });
});
