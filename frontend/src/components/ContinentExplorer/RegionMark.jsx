import React from 'react';

// A single-country unit shows its flag; a region (Andino, Magreb…) shows its group color, never a flag.
const RegionMark = ({ row, color, className, width, height }) => (row.flag ? (
  <img
    className={className}
    src={`https://flagcdn.com/w40/${row.flag.toLowerCase()}.png`}
    srcSet={`https://flagcdn.com/w80/${row.flag.toLowerCase()}.png 2x`}
    alt=""
    width={width}
    height={height}
  />
) : (
  <span
    className={className}
    aria-hidden="true"
    style={{ display: 'inline-block', width: height, height, borderRadius: '50%', background: color || '#8E7AA3' }}
  />
));

export default RegionMark;
