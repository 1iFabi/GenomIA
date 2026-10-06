import React, { Suspense, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSession } from '../hooks/useSession';
import DashboardSkeleton from './DashboardSkeleton/DashboardSkeleton';

export default function ProtectedRoute({ children, requireService = true, requireAdmin = false }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading } = useSession(location.pathname);
  const isDashboardRoute =
    location.pathname === '/dashboard' || location.pathname.startsWith('/dashboard/');

  const serviceStatus = user?.service_status;
  // Staff never buy a service; only clients are gated by purchase state.
  const gateService = requireService && DashboardSkeleton.getRoleVariant(user) === 'user';
  let redirectTo = null;
  if (!loading) {
    if (!user) {
      redirectTo = '/login';
    } else if (requireAdmin && user.is_staff !== true) {
      redirectTo = '/dashboard';
    } else if (gateService && serviceStatus === 'NO_PURCHASED' && location.pathname !== '/no-purchased') {
      redirectTo = '/no-purchased';
    } else if (gateService && serviceStatus === 'PENDING' && location.pathname !== '/pending') {
      redirectTo = '/pending';
    } else if (location.pathname === '/no-purchased' && serviceStatus !== 'NO_PURCHASED') {
      redirectTo = '/dashboard';
    } else if (location.pathname === '/pending' && serviceStatus === 'COMPLETED') {
      redirectTo = '/dashboard';
    }
  }

  useEffect(() => {
    if (redirectTo) navigate(redirectTo, { replace: true });
  }, [navigate, redirectTo]);

  if (loading) {
    return isDashboardRoute ? <DashboardSkeleton variant="neutral" /> : null;
  }
  // Recompute authorization on every render; never retain a previous guard's "ok".
  if (redirectTo) return null;

  const protectedChildren = isDashboardRoute && React.isValidElement(children)
    ? React.cloneElement(children, { user })
    : children;

  return isDashboardRoute ? (
    <Suspense fallback={<DashboardSkeleton variant={DashboardSkeleton.getRoleVariant(user)} />}>
      {protectedChildren}
    </Suspense>
  ) : protectedChildren;
}
