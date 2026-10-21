import React from 'react';

// Two strands crossing twice, with the rungs between them: the helix of the dashboard, drawn flat.
const STRAND_A = 'M14 6 C 34 14, 34 20, 24 24 S 14 34, 34 42';
const STRAND_B = 'M34 6 C 14 14, 14 20, 24 24 S 34 34, 14 42';
const RUNGS = [[18, 10, 30, 10], [20, 17, 28, 17], [20, 31, 28, 31], [18, 38, 30, 38]];

/** A generated avatar in the page's one colour: the reader's initial or the helix. Its size is the CSS --s. */
const Avatar = ({ figure, initial }) => (
  <span className="avatar" aria-hidden="true">
    {figure === 'helix' ? (
      <svg viewBox="0 0 48 48" width="62%" height="62%">
        {RUNGS.map(([x1, y1, x2, y2]) => <line key={y1} x1={x1} y1={y1} x2={x2} y2={y2} className="avatar__rung" strokeWidth="2.5" strokeLinecap="round" />)}
        <path d={STRAND_A} fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
        <path d={STRAND_B} fill="none" className="avatar__strand" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
    ) : (
      <span>{initial}</span>
    )}
  </span>
);

export default Avatar;
