import React from 'react';

// Componente de mensaje de error reutilizable
// Props:
// - message: string (mensaje a mostrar)
// - className: string opcional para estilos adicionales
// - small: boolean opcional para tamaño compacto (por defecto true)
const ErrorCard = ({ message = 'Error - Credenciales Incorrectas.', className = '', small = true }) => {
  return (
    <div
      role="alert"
      style={{
        backgroundColor: '#fee2e2',
        borderLeft: '4px solid #f87171',
        color: '#991b1b',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        transition: 'all 0.2s ease-in-out',
        padding: small ? '8px' : '12px',
        fontSize: small ? '12px' : '14px'
      }}
      className={className}
    >
      <svg 
        stroke="currentColor" 
        viewBox="0 0 24 24" 
        fill="none" 
        style={{
          height: '20px',
          width: '20px',
          flexShrink: 0,
          marginRight: '8px',
          color: '#f87171'
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M13 16h-1v-4h1m0-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <p style={{ fontWeight: 600, margin: 0 }}>{message}</p>
    </div>
  );
}

export default ErrorCard;
