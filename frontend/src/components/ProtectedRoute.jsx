import React, { Suspense, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSession } from '../hooks/useSession';
import DashboardSkeleton from './DashboardSkeleton/DashboardSkeleton';
import RasgosLoading from '../pages/Rasgos/RasgosLoading';

export default function ProtectedRoute({ children, requireService = true, requireAdmin = false }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading } = useSession(location.pathname);
  const isDashboardRoute =
    location.pathname === '/dashboard' || location.pathname.startsWith('/dashboard/');
  const isRasgosRoute = location.pathname.replace(/\/+$/, '') === '/dashboard/rasgos';

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
      // ponytail: every client without service lands here, not only on first login (a "just registered" flag needs backend data).
      redirectTo = '/';
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
    if (!isDashboardRoute) return null;
    return isRasgosRoute
      ? <RasgosLoading />
      : <DashboardSkeleton variant="neutral" pathname={location.pathname} />;
  }
  // Recompute authorization on every render; never retain a previous guard's "ok".
  if (redirectTo) return null;

  const protectedChildren = isDashboardRoute && React.isValidElement(children)
    ? React.cloneElement(children, { user })
    : children;

  return isDashboardRoute ? (
    <Suspense fallback={isRasgosRoute
      ? <RasgosLoading />
      : <DashboardSkeleton variant={DashboardSkeleton.getRoleVariant(user)} pathname={location.pathname} />}>
      {protectedChildren}
    </Suspense>
  ) : protectedChildren;
}
