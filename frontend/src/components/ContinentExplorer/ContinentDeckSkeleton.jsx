import React from 'react';
import './ContinentDeck.css';

const Bar = ({ className }) => <span className={`cdeck-skel ${className}`} />;

// The deck while the results load, from the deck's own classes: the first card in the middle, the next one
// peeking, so the globe above already has its final height and nothing moves when the cards arrive.
const ContinentDeckSkeleton = () => (
  <ul className="cdeck cdeck--loading" aria-hidden="true">
    {[0, 1].map((i) => (
      <li key={i} className="cdeck__card" aria-current={i === 0 ? 'true' : undefined}>
        <div className="cdeck__head">
          <span className="cdeck__name"><Bar className="cdeck-skel--name" /></span>
          <span className="cdeck__count"><Bar className="cdeck-skel--count" /></span>
          <Bar className="cdeck__shape cdeck-skel--shape" />
        </div>
        <p className="cdeck__share"><Bar className="cdeck-skel--share" /></p>
        <div className="cdeck__rows">
          <span className="cdeck-skel__row">
            <Bar className="cdeck-skel--flag" />
            <span className="cdeck__country"><Bar className="cdeck-skel--country" /><Bar className="cdeck-skel--pop" /></span>
            <Bar className="cdeck-skel--value" />
          </span>
        </div>
      </li>
    ))}
  </ul>
);

export default ContinentDeckSkeleton;
