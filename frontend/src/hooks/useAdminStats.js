import { useState, useEffect } from 'react';
import { apiRequest, API_ENDPOINTS } from '../config/api';

export const useAdminStats = () => {
  const [stats, setStats] = useState({
    totalUsers: 0,
    pendingReports: 0,
    completedAnalysis: 0,
    lastUpdate: 'Hoy',
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        
        const response = await apiRequest(API_ENDPOINTS.ADMIN_STATS, { method: 'GET' });
        
        if (response.ok && response.data) {
          const data = response.data;
          
          // Extraer datos del dashboard - se envían en el payload raíz
          setStats({
            totalUsers: data.total_users || 0,
            pendingReports: data.pending_reports || 0,
            completedAnalysis: data.analysis_count || 0,
            lastUpdate: data.last_update || 'Hoy',
          });
          setError(null);
        } else {
          console.warn('No dashboard data available');
          setError('No se pudieron cargar las estadísticas');
        }
      } catch (err) {
        console.error('Error fetching admin stats:', err);
        setError(err);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    
    // Actualizar estadísticas cada 60 segundos
    const interval = setInterval(fetchStats, 60000);
    return () => clearInterval(interval);
  }, []);

  return { stats, loading, error };
};
