import React from 'react';
import './SectionHeader.css';

const SectionHeader = ({ 
  title, 
  subtitle, 
  icon: Icon = null 
}) => {
  return (
    <header className="section-header">
      <div className="section-header__content">
        {Icon && (
          <div className="section-header__icon">
            <Icon size={28} />
          </div>
        )}
        <div className="section-header__text">
          <h1 className="section-header__title">{title}</h1>
          {subtitle && (
            <p className="section-header__subtitle">{subtitle}</p>
          )}
        </div>
      </div>
    </header>
  );
};

export default SectionHeader;
