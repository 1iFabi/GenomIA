import React, { act, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useLatestGenomicsResults } from './useLatestGenomicsResults';

const service = (id = 'latest', purchasedAt = '2026-09-24T12:00:00Z', version = '1') => ({
  service_request_id: id,
  purchased_at: purchasedAt,
  release_version: version,
  synthetic: true,
  non_clinical: true,
  disclaimer: 'Synthetic placeholders, not evaluated.',
});
const latest = service();
const older = service('older', '2026-09-23T12:00:00Z', '99');
const payload = (selected = latest, results = [{ module: 'traits', payload: { state: 'not_evaluated' } }]) => ({
  ...selected,
  results,
});
const reply = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { 'Content-Type': 'application/json' },
});
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

let root;
let container;
let state;
let renders;

const mount = async (strict = false) => {
  const Probe = () => {
    state = useLatestGenomicsResults();
    renders.push(state);
    return null;
  };
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(strict ? <StrictMode><Probe /></StrictMode> : <Probe />));
};
const settle = async (pending, response) => {
  await act(async () => pending.resolve(response));
};
const expectCleared = (status, error = null) => {
  expect(state).toMatchObject({ status, loading: status === 'loading', service: null, data: null, error });
};

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', vi.fn());
  state = null;
  renders = [];
});
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container?.remove();
  container = null;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useLatestGenomicsResults', () => {
  it('starts loading and selects the newest purchase, not version or untied list position', async () => {
    const pending = deferred();
    fetch.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(reply(payload()));
    await mount();
    expectCleared('loading');

    await settle(pending, reply({ services: [older, latest, service('oldest', '2025-01-01T00:00:00Z', '100')] }));

    expect(state).toMatchObject({ status: 'ready', loading: false, service: latest, data: payload(), error: null });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/genoma/v1/services/', '/api/genoma/v1/services/latest/results/',
    ]);
  });

  it.each([
    ['microseconds', '2026-09-24T12:00:00.123001Z', '2026-09-24T12:00:00.123999Z'],
    ['different precision', '2026-09-24T12:00:00.9Z', '2026-09-24T12:00:00.900001Z'],
    ['seconds', '2026-09-24T12:00:00.999999Z', '2026-09-24T12:00:01Z'],
    ['UTC offset form', '2026-09-24T12:00:00Z', '2026-09-24T12:00:01+00:00'],
    ['leap day', '2024-02-28T23:59:59Z', '2024-02-29T00:00:00Z'],
  ])('preserves valid timestamp ordering: %s', async (_label, earlier, later) => {
    const selected = service('newest', later);
    fetch.mockResolvedValueOnce(reply({ services: [service('earlier', earlier), selected] }))
      .mockResolvedValueOnce(reply(payload(selected)));
    await mount();
    expect(state.service).toEqual(selected);
    expect(state.status).toBe('ready');
  });

  it('keeps the first canonical backend entry among equal latest timestamps', async () => {
    const first = service('canonical-first', '2026-09-24T12:00:00.123Z', '1');
    const tied = service('z-id', '2026-09-24T12:00:00.123000+00:00', '100');
    fetch.mockResolvedValueOnce(reply({ services: [older, first, tied] }))
      .mockResolvedValueOnce(reply(payload(first)));
    await mount();
    expect(state.service).toEqual(first);
    expect(fetch.mock.calls[1][0]).toContain('/canonical-first/results/');
  });

  it('exposes an empty eligible list without fetching results or creating demo data', async () => {
    fetch.mockResolvedValueOnce(reply({ services: [] }));
    await mount();
    expectCleared('empty');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  const malformedLists = [
    ['null envelope', null], ['array envelope', []], ['missing services', {}],
    ['non-array services', { services: {} }], ['null entry', { services: [null] }],
    ['array entry', { services: [[]] }], ['missing ID', { services: [{ purchased_at: latest.purchased_at }] }],
    ['numeric ID', { services: [{ ...latest, service_request_id: 123 }] }],
    ['empty ID', { services: [{ ...latest, service_request_id: '' }] }],
    ['blank ID', { services: [{ ...latest, service_request_id: '  ' }] }],
    ['missing timestamp', { services: [{ service_request_id: 'missing-date' }] }],
    ['numeric timestamp', { services: [{ ...latest, purchased_at: 123 }] }],
    ...[
      '', 'not-a-date', '2026-09-24', '2026-09-24T12:00:00', '2026-09-24T12:00:00-03:00',
      '2026-09-24T12:00:00+01:00', '2026-02-30T12:00:00Z', '2025-02-29T00:00:00Z',
      '2026-13-01T00:00:00Z', '2026-09-24T24:00:00Z', '2026-09-24T12:60:00Z',
      '2026-09-24T12:00:60Z', ' 2026-09-24T12:00:00Z', '0000-01-01T00:00:00Z',
      '2026-09-24T12:00:00Z\n',
    ].map((date) => [`invalid UTC timestamp: ${date}`, { services: [{ ...latest, purchased_at: date }] }]),
    ['malformed older entry', { services: [latest, { ...older, purchased_at: 'invalid' }] }],
  ];
  it.each(malformedLists)('fails closed on %s', async (_label, data) => {
    fetch.mockResolvedValueOnce(reply(data));
    await mount();
    expectCleared('error', { kind: 'invalid_data', resource: 'services', status: 200 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retains raw results and all synthetic/non-clinical disclosure without interpreting values', async () => {
    const raw = { ...payload(), provenance: { source: 'bundled synthetic fixture' } };
    fetch.mockResolvedValueOnce(reply({ services: [latest] })).mockResolvedValueOnce(reply(raw));
    await mount();
    expect(state.data).toEqual(raw);
    expect(state.data).not.toHaveProperty('clinical_interpretation');
  });

  it('retains the selected service and raw disclosure when results are empty', async () => {
    const raw = payload(latest, []);
    fetch.mockResolvedValueOnce(reply({ services: [latest] })).mockResolvedValueOnce(reply(raw));
    await mount();
    expect(state).toMatchObject({ status: 'empty', loading: false, service: latest, data: raw, error: null });
  });

  it.each([
    ['null envelope', null], ['array envelope', []], ['missing results', { service_request_id: 'latest' }],
    ['null results', { service_request_id: 'latest', results: null }],
    ['non-array results', { service_request_id: 'latest', results: {} }],
    ['missing service ID', { results: [] }], ['wrong service ID', payload(older)],
    ['numeric service ID', { service_request_id: 123, results: [] }],
  ])('fails closed on results with %s without selecting an older service', async (_label, data) => {
    fetch.mockResolvedValueOnce(reply({ services: [older, latest] })).mockResolvedValueOnce(reply(data));
    await mount();
    expectCleared('error', { kind: 'invalid_data', resource: 'results', status: 200 });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1][0]).toContain('/latest/results/');
  });

  it.each(['services', 'results'].flatMap((resource) =>
    [401, 403, 404, 500].map((status) => [resource, status]),
  ))('classifies %s HTTP %s without legacy fallback', async (resource, status) => {
    if (resource === 'results') fetch.mockResolvedValueOnce(reply({ services: [older, latest] }));
    fetch.mockResolvedValueOnce(reply({ error: 'unavailable' }, status));
    await mount();
    expectCleared(status === 401 || status === 403 ? 'permission' : 'error', { kind: 'http', resource, status });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(resource === 'services'
      ? ['/api/genoma/v1/services/']
      : ['/api/genoma/v1/services/', '/api/genoma/v1/services/latest/results/']);
  });

  it.each(['services', 'results'])('classifies %s network failure as connection error', async (resource) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    if (resource === 'results') fetch.mockResolvedValueOnce(reply({ services: [older, latest] }));
    fetch.mockRejectedValueOnce(new TypeError('Network unavailable'));
    await mount();
    expectCleared('error', { kind: 'connection', resource, status: 0 });
    expect(fetch).toHaveBeenCalledTimes(resource === 'services' ? 1 : 2);
  });

  it('uses cookie-authenticated GET and one-pass encoding through the existing helpers', async () => {
    const selected = service('request/a b?#%+á%2F');
    fetch.mockResolvedValueOnce(reply({ services: [selected] })).mockResolvedValueOnce(reply(payload(selected)));
    await mount();
    expect(state.status).toBe('ready');
    expect(fetch.mock.calls).toEqual([
      ['/api/genoma/v1/services/', { method: 'GET', credentials: 'include', headers: {} }],
      ['/api/genoma/v1/services/request%2Fa%20b%3F%23%25%2B%C3%A1%252F/results/',
        { method: 'GET', credentials: 'include', headers: {} }],
    ]);
  });

  it('clears selected service, data and errors immediately on retry and recovers using a fresh list', async () => {
    const retryList = deferred();
    fetch.mockResolvedValueOnce(reply({ services: [latest] })).mockResolvedValueOnce(reply(payload()))
      .mockReturnValueOnce(retryList.promise);
    await mount();
    const retry = state.retry;
    await act(async () => retry());
    expectCleared('loading');
    expect(state.retry).toBe(retry);
    await settle(retryList, reply({ error: 'blocked' }, 403));
    expectCleared('permission', { kind: 'http', resource: 'services', status: 403 });

    const retryResults = deferred();
    const selected = service('new-purchase', '2026-10-01T00:00:00Z');
    fetch.mockResolvedValueOnce(reply({ services: [selected] })).mockReturnValueOnce(retryResults.promise);
    await act(async () => retry());
    expectCleared('loading');
    await settle(retryResults, reply(payload(selected)));
    expect(state).toMatchObject({ status: 'ready', service: selected, data: payload(selected), error: null });
  });

  it('does not retain stale data after a retry results error', async () => {
    fetch.mockResolvedValueOnce(reply({ services: [latest] })).mockResolvedValueOnce(reply(payload()));
    await mount();
    fetch.mockResolvedValueOnce(reply({ services: [older, latest] })).mockResolvedValueOnce(reply({}, 404));
    await act(async () => state.retry());
    expectCleared('error', { kind: 'http', resource: 'results', status: 404 });
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it('ignores an obsolete list completion rather than fetching its results', async () => {
    const obsolete = deferred();
    fetch.mockReturnValueOnce(obsolete.promise).mockResolvedValueOnce(reply({ services: [latest] }))
      .mockResolvedValueOnce(reply(payload()));
    await mount();
    await act(async () => state.retry());
    const current = state;
    await settle(obsolete, reply({ services: [older] }));
    expect(state).toBe(current);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it.each(['success', 'http failure', 'network failure'])('ignores obsolete results: %s', async (outcome) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const obsolete = deferred();
    fetch.mockResolvedValueOnce(reply({ services: [older] })).mockReturnValueOnce(obsolete.promise)
      .mockResolvedValueOnce(reply({ services: [latest] })).mockResolvedValueOnce(reply(payload()));
    await mount();
    await act(async () => state.retry());
    const current = state;
    await act(async () => {
      if (outcome === 'network failure') obsolete.reject(new TypeError('offline'));
      else obsolete.resolve(reply(outcome === 'success' ? payload(older) : {}, outcome === 'success' ? 200 : 403));
    });
    expect(state).toBe(current);
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it('invalidates pending results immediately, including consecutive retries before rerender', async () => {
    const obsoleteResults = deferred();
    const obsoleteList = deferred();
    const currentList = deferred();
    fetch.mockResolvedValueOnce(reply({ services: [older] })).mockReturnValueOnce(obsoleteResults.promise)
      .mockReturnValueOnce(obsoleteList.promise).mockReturnValueOnce(currentList.promise)
      .mockResolvedValueOnce(reply(payload()));
    await mount();
    await act(async () => { state.retry(); state.retry(); });
    expectCleared('loading');
    const current = state;
    await settle(obsoleteResults, reply(payload(older)));
    await settle(obsoleteList, reply({}, 403));
    expect(state).toBe(current);
    expectCleared('loading');
    await settle(currentList, reply({ services: [latest] }));
    expect(state).toMatchObject({ status: 'ready', service: latest, data: payload() });
    expect(fetch).toHaveBeenCalledTimes(5);
  });

  it.each(['services', 'results'])('ignores pending %s completion after unmount', async (resource) => {
    const pending = deferred();
    if (resource === 'results') fetch.mockResolvedValueOnce(reply({ services: [latest] }));
    fetch.mockReturnValueOnce(pending.promise);
    await mount();
    const retry = state.retry;
    await act(async () => root.unmount());
    root = null;
    const renderCount = renders.length;
    await settle(pending, reply(resource === 'services' ? { services: [latest] } : payload()));
    await act(async () => retry());
    expect(renders).toHaveLength(renderCount);
    expect(fetch).toHaveBeenCalledTimes(resource === 'services' ? 1 : 2);
  });

  it('is StrictMode safe when the discarded mount request completes late', async () => {
    const obsolete = deferred();
    fetch.mockReturnValueOnce(obsolete.promise).mockResolvedValueOnce(reply({ services: [latest] }))
      .mockResolvedValueOnce(reply(payload()));
    await mount(true);
    expect(state.status).toBe('ready');
    const current = state;
    await settle(obsolete, reply({ services: [older] }));
    expect(state).toBe(current);
    expect(fetch).toHaveBeenCalledTimes(3);
  });
});
