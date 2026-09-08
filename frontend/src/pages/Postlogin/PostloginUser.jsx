import React, { useEffect, useState } from 'react';
import { useNavigate, Routes, Route } from 'react-router-dom';
import Dashboard from './Dashboard';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Ancestria from '../Ancestria/Ancestria';
import Rasgos from '../Rasgos/Rasgos';
import Enfermedades from '../Enfermedades/Enfermedades';
import Biometrics from '../Biometrics/Biometrics';
import Biomarcadores from '../Biomarcadores/Biomarcadores';
import Farmacogenetica from '../Farmacogenetica/Farmacogenetica';

const PostloginUser = ({ user: initialUser }) => {
  const [user, setUser] = useState(initialUser);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (error) {
      console.error('Error al cerrar sesion', error);
    }
    clearToken();
    navigate('/');
  };

  const handleDownload = () => {
    // TODO: Integrar descarga cuando el endpoint este disponible.
  };

  return (
    <Routes>
      <Route path="/" element={<Dashboard user={user} onLogout={handleLogout} onDownload={handleDownload} />} />
      <Route path="ancestria" element={<Ancestria />} />
      <Route path="rasgos" element={<Rasgos />} />
      <Route path="enfermedades" element={<Enfermedades />} />
      <Route path="farmacogenetica" element={<Farmacogenetica/>} />
      <Route path="biomarcadores" element={<Biomarcadores/>} />
      <Route path="biometricas" element={<Biometrics />} />
    </Routes>
  );
};

export default PostloginUser;
