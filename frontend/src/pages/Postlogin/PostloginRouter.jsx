import React from 'react';
import { Navigate, Routes, Route } from 'react-router-dom';
import DashboardSkeleton from '../../components/DashboardSkeleton/DashboardSkeleton';
import PostloginUser from './PostloginUser';
import PostloginAnalyst from './PostloginAnalyst';
import PostloginReception from './PostloginReception';
import AdminOverview from '../Admin/AdminOverview';
import AdminUsers from '../Admin/AdminUsers';
import AdminActivity from '../Admin/AdminActivity';
import Enfermedades from '../Enfermedades/Enfermedades';
import Farmacogenetica from '../Farmacogenetica/Farmacogenetica';
import GenominWidget from '../../components/Genomin/GenominWidget';

const PostloginRouter = ({ user }) => {
  const role = DashboardSkeleton.getRoleVariant(user);

  if (role === 'admin') {
    return (
      <Routes>
        <Route path="/" element={<AdminOverview />} />
        <Route path="admin/usuarios" element={<AdminUsers />} />
        <Route path="admin/actividad" element={<AdminActivity />} />
        {/* The old role-management page now lives in Usuarios. */}
        <Route path="admin/analysts" element={<Navigate to="/dashboard/admin/usuarios" replace />} />
        <Route path="enfermedades" element={<Enfermedades />} />
        <Route path="farmacogenetica" element={<Farmacogenetica />} />
      </Routes>
    );
  }

  if (role === 'analyst') {
    return (
      <Routes>
        <Route path="/" element={<PostloginAnalyst user={user} mode="analyst" />} />
        <Route path="enfermedades" element={<Enfermedades />} />
        <Route path="farmacogenetica" element={<Farmacogenetica />} />
      </Routes>
    );
  }

  if (role === 'reception') {
    return (
      <Routes>
        <Route path="/" element={<PostloginReception user={user} />} />
      </Routes>
    );
  }

  return (
    <>
      <PostloginUser user={user} />
      <GenominWidget />
    </>
  );
};

export default PostloginRouter;
