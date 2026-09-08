import React from 'react';
import './SkeletonCard.css';

const SkeletonCard = () => {
  return (
    <div className="skeleton-card">
      <div className="skeleton-line skeleton-line--title"></div>
      <div className="skeleton-line skeleton-line--text"></div>
      <div className="skeleton-line skeleton-line--text"></div>
    </div>
  );
};

export default SkeletonCard;
