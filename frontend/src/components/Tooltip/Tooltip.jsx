import React, { useState, useRef } from 'react';
import './Tooltip.css';

const Tooltip = ({ content, children }) => {
    const [isVisible, setIsVisible] = useState(false);

    return (
        <span className="tooltip-wrapper" onMouseEnter={() => setIsVisible(true)} onMouseLeave={() => setIsVisible(false)}>
            {children}
            {isVisible && (
                <div className="tooltip-content">
                    {content}
                </div>
            )}
        </span>
    );
};

export default Tooltip;
