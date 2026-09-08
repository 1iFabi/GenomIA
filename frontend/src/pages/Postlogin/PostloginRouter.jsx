import React, { useEffect, useState } from 'react';
import { useNavigate, Routes, Route } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import PostloginUser from './PostloginUser';
import PostloginAdmin from './PostloginAdmin';
import PostloginAnalyst from './PostloginAnalyst';
import PostloginReception from './PostloginReception';
import AdminReports from './AdminReports';
import AdminVariantsDatabase from './AdminVariantsDatabase';
import AdminAnalystAccess from './AdminAnalystAccess';
import Biomarcadores from '../Biomarcadores/Biomarcadores';
import Biometrics from '../Biometrics/Biometrics';
import Enfermedades from '../Enfermedades/Enfermedades';
import Farmacogenetica from '../Farmacogenetica/Farmacogenetica';
import NalaWidget from '../../components/Nala/NalaWidget';

const PostloginRouter = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let mounted = true;

    (async () => {
      const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (!mounted) return;

      if (!response.ok) {
        navigate('/login', { replace: true });
        return;
      }

      setUser(response.data.user ?? response.data);
      setLoading(false);
    })();

    return () => {
      mounted = false;
    };
  }, [navigate]);

  if (loading) {
    return null;
  }

  const roles = user?.roles || [];
  const isAdmin = user?.is_admin || user?.is_staff || roles.includes('ADMIN');
  const isAnalyst = user?.is_analyst || roles.includes('ANALISTA');
  const isReception = user?.is_reception || roles.includes('RECEPCION');

  if (isAdmin) {
    return (
      <Routes>
        <Route path="/" element={<PostloginAdmin user={user} mode="admin" />} />
        <Route path="admin/reports" element={<AdminReports user={user} />} />
        <Route path="admin/variants" element={<AdminVariantsDatabase user={user} />} />
        <Route path="admin/analysts" element={<AdminAnalystAccess user={user} />} />
        <Route path="biomarcadores" element={<Biomarcadores />} />
        <Route path="biometricas" element={<Biometrics />} />
        <Route path="enfermedades" element={<Enfermedades />} />
        <Route path="farmacogenetica" element={<Farmacogenetica />} />
      </Routes>
    );
  }

  if (isAnalyst) {
    return (
      <Routes>
        <Route path="/" element={<PostloginAnalyst user={user} mode="analyst" />} />
        <Route path="admin/reports" element={<AdminReports user={user} />} />
        <Route path="admin/variants" element={<AdminVariantsDatabase user={user} />} />
        <Route path="biomarcadores" element={<Biomarcadores />} />
        <Route path="biometricas" element={<Biometrics />} />
        <Route path="enfermedades" element={<Enfermedades />} />
        <Route path="farmacogenetica" element={<Farmacogenetica />} />
      </Routes>
    );
  }

  if (isReception) {
    return (
      <Routes>
        <Route path="/" element={<PostloginReception user={user} />} />
      </Routes>
    );
  }

  return (
    <>
      <PostloginUser user={user} />
      <NalaWidget />
    </>
  );
};

export default PostloginRouter;
