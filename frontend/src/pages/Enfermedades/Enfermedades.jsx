import React from 'react';
import { useLocation } from 'react-router-dom';
import Monogenico from '../Monogenico/Monogenico';
import Poligenico from '../Poligenico/Poligenico';

// Both risks share /dashboard/enfermedades; the hash picks which page, poligénico when none.
const Enfermedades = () => {
  const { hash } = useLocation();
  return hash === '#monogenic_risk' ? <Monogenico /> : <Poligenico />;
};

export default Enfermedades;
