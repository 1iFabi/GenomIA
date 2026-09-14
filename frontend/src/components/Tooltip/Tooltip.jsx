import React, { cloneElement, isValidElement, useId, useState } from 'react';
import './Tooltip.css';

const hasTextContent = (node) => React.Children.toArray(node).some((child) => {
    if (typeof child === 'string' || typeof child === 'number') {
        return String(child).trim().length > 0;
    }

    return isValidElement(child) && hasTextContent(child.props.children);
});

const isSvgStyleTrigger = (node) => {
    if (!isValidElement(node)) return false;
    if (node.type === 'svg') return true;

    const typeName = typeof node.type === 'function'
        ? node.type.displayName || node.type.name
        : node.type?.displayName;
    const hasIconProps = node.props.size !== undefined || node.props.strokeWidth !== undefined;

    return Boolean(typeName && /(icon|lucide)/i.test(typeName))
        || hasIconProps
        || React.Children.toArray(node.props.children).some(isSvgStyleTrigger);
};

const hasAccessibleName = (node) => {
    if (!isValidElement(node)) return false;

    const { 'aria-label': ariaLabel, 'aria-labelledby': ariaLabelledBy, title } = node.props;
    return [ariaLabel, ariaLabelledBy, title].some((value) => (
        typeof value === 'string' ? value.trim().length > 0 : Boolean(value)
    )) || hasTextContent(node.props.children);
};

const Tooltip = ({ content, children }) => {
    const [isHovered, setIsHovered] = useState(false);
    const [isFocused, setIsFocused] = useState(false);
    const tooltipId = `tooltip-${useId().replace(/:/g, '')}`;
    const isVisible = isHovered || isFocused;

    const handleFocus = (event) => {
        children?.props?.onFocus?.(event);
        setIsFocused(true);
    };

    const handleBlur = (event) => {
        children?.props?.onBlur?.(event);
        setIsFocused(false);
    };

    const existingDescribedBy = isValidElement(children)
        ? children.props['aria-describedby']
        : undefined;
    const describedBy = isFocused
        ? [existingDescribedBy, tooltipId].filter(Boolean).join(' ')
        : existingDescribedBy;
    const needsGenericAccessibleName = isValidElement(children)
        && isSvgStyleTrigger(children)
        && !hasTextContent(children.props.children)
        && !hasAccessibleName(children);
    const triggerProps = {
        onFocus: handleFocus,
        onBlur: handleBlur,
        'aria-describedby': describedBy || undefined,
        ...(needsGenericAccessibleName ? { 'aria-label': 'Más información' } : {}),
        tabIndex: isValidElement(children) ? children.props.tabIndex ?? 0 : 0,
    };

    const trigger = isValidElement(children) && children.type !== React.Fragment
        ? cloneElement(children, triggerProps)
        : <span {...triggerProps}>{children}</span>;

    return (
        <span
            className="tooltip-wrapper"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {trigger}
            {isVisible && (
                <div id={tooltipId} className="tooltip-content" role="tooltip" aria-hidden={!isFocused}>
                    {content}
                </div>
            )}
        </span>
    );
};

export default Tooltip;
