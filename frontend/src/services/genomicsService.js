import { API_ENDPOINTS, apiRequest } from '../config/api';

export const getGenomicsServices = () =>
  apiRequest(API_ENDPOINTS.GENOMICS_SERVICES, { method: 'GET' });

export const getGenomicsServiceResults = (serviceRequestId) =>
  apiRequest(API_ENDPOINTS.GENOMICS_SERVICE_RESULTS(serviceRequestId), { method: 'GET' });

export const getGenomicsServiceMetrics = (serviceRequestId) =>
  apiRequest(API_ENDPOINTS.GENOMICS_SERVICE_METRICS(serviceRequestId), { method: 'GET' });
