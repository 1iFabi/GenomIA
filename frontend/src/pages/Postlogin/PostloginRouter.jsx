import React from 'react';
import { Routes, Route } from 'react-router-dom';
import DashboardSkeleton from '../../components/DashboardSkeleton/DashboardSkeleton';
import PostloginUser from './PostloginUser';
import PostloginAdmin from './PostloginAdmin';
import PostloginAnalyst from './PostloginAnalyst';
import PostloginReception from './PostloginReception';
import AdminAnalystAccess from './AdminAnalystAccess';
import Enfermedades from '../Enfermedades/Enfermedades';
import Farmacogenetica from '../Farmacogenetica/Farmacogenetica';
import NalaWidget from '../../components/Nala/NalaWidget';

const PostloginRouter = ({ user }) => {
  const role = DashboardSkeleton.getRoleVariant(user);

  if (role === 'admin') {
    return (
      <Routes>
        <Route path="/" element={<PostloginAdmin user={user} mode="admin" />} />
        <Route path="admin/analysts" element={<AdminAnalystAccess user={user} />} />
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
      <NalaWidget />
    </>
  );
};

export default PostloginRouter;
