import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, expect, it, vi } from 'vitest';
import ContinentDeck from './ContinentDeck';

const continents = [
  { key: 'Europe', label: 'Europa', proportion: 0.6, countries: 1, rows: [{ population: 'IBS', places: [{ code: 'ES', name: 'España' }], label: 'Ibérico', group: 'EUR', proportion: 0.6 }] },
  { key: 'South America', label: 'Sudamérica', proportion: 0.4, countries: 2, rows: [{ population: 'AMR_ANDES', places: [{ code: 'CL', name: 'Chile' }, { code: 'AR', name: 'Argentina' }], label: 'Andino', group: 'AMR', proportion: 0.4 }] },
];
let root;
let container;

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

it('swiping to a card picks its continent, and a country row opens it', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const onPick = vi.fn();
  const onOpenCountry = vi.fn();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(
    <ContinentDeck continents={continents} shapes={{}} groups={[]} active="Europe" onPick={onPick} onOpenCountry={onOpenCountry} />,
  ));
  expect(container.querySelector('.cdeck__card').textContent).toContain('1 país');
  const deck = container.querySelector('.cdeck');
  Object.defineProperty(deck.children[0], 'offsetLeft', { value: 0 });
  Object.defineProperty(deck.children[1], 'offsetLeft', { value: 300 });
  deck.scrollLeft = 320;
  await act(async () => deck.dispatchEvent(new Event('scroll')));
  expect(onPick).toHaveBeenCalledWith('South America');

  await act(async () => container.querySelector('.cdeck__rows button').click());
  expect(onOpenCountry).toHaveBeenCalledWith({ ...continents[0].rows[0], country_code: 'ES' });
});
