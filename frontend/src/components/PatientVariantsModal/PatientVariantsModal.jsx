import React, { useState, useEffect, useMemo } from 'react';
import { X, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { API_ENDPOINTS, apiRequest } from '../../config/api';
import './PatientVariantsModal.css';

export default function PatientVariantsModal({ isOpen, onClose, patient }) {
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Función para capitalizar primera letra
  const capitalize = (str) => {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  };

  useEffect(() => {
    if (isOpen && patient) {
      fetchVariants();
    }
  }, [isOpen, patient]);

  const fetchVariants = async () => {
    setLoading(true);
    try {
      console.log('Fetching variants for patient:', patient);
      console.log('User ID:', patient.userId);
      
      const response = await apiRequest(
        API_ENDPOINTS.PATIENT_VARIANTS(patient.userId),
        { method: 'GET' }
      );

      console.log('Response:', response);

      if (response.ok && response.data.success) {
        console.log('Variants received:', response.data.data.variants.length);
        setVariants(response.data.data.variants || []);
      } else {
        console.error('Error fetching variants:', response.data);
        alert(`Error al cargar variantes: ${response.data.error || 'Error desconocido'}`);
      }
    } catch (error) {
      console.error('Error fetching variants:', error);
      alert('Error de conexión al cargar variantes');
    } finally {
      setLoading(false);
    }
  };

  // Filtrado
  const filteredVariants = useMemo(() => {
    return variants.filter((variant) => {
      const matchesSearch = 
        variant.rsid?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        variant.fenotipo?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        variant.cromosoma?.toLowerCase().includes(searchTerm.toLowerCase());
      
      const matchesCategory = 
        categoryFilter === 'all' || 
        variant.categoria?.toLowerCase() === categoryFilter.toLowerCase();
      
      return matchesSearch && matchesCategory;
    });
  }, [variants, searchTerm, categoryFilter]);

  // Paginación
  const totalPages = Math.ceil(filteredVariants.length / itemsPerPage);
  const paginatedVariants = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return filteredVariants.slice(startIndex, startIndex + itemsPerPage);
  }, [filteredVariants, currentPage]);

  // Resetear página al cambiar filtros
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, categoryFilter]);

  // Categorías únicas
  const categories = useMemo(() => {
    const cats = [...new Set(variants.map(v => v.categoria).filter(Boolean))];
    return cats.sort();
  }, [variants]);

  if (!isOpen) return null;

  return (
    <div className="patient-variants-modal__overlay" onClick={onClose}>
      <div className="patient-variants-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="patient-variants-modal__header">
          <div className="patient-variants-modal__header-content">
            <h2 className="patient-variants-modal__title">
              Variantes Genéticas - {patient?.name}
            </h2>
            <p className="patient-variants-modal__subtitle">
              {patient?.email} • {variants.length} variantes totales
            </p>
          </div>
          <button
            className="patient-variants-modal__close-btn"
            onClick={onClose}
            aria-label="Cerrar modal"
          >
            <X size={24} />
          </button>
        </div>

        {/* Filters */}
        <div className="patient-variants-modal__filters">
          <div className="patient-variants-modal__search">
            <Search size={18} className="patient-variants-modal__search-icon" />
            <input
              type="text"
              placeholder="Buscar por rsID, fenotipo o cromosoma..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="patient-variants-modal__search-input"
            />
          </div>

          <div className="patient-variants-modal__filter-group">
            <label className="patient-variants-modal__filter-label">Categoría:</label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="patient-variants-modal__filter-select"
            >
              <option value="all">Todas</option>
              {categories.map(cat => (
                <option key={cat} value={cat}>{capitalize(cat)}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Content */}
        <div className="patient-variants-modal__content">
          {loading ? (
            <div className="patient-variants-modal__loading">
              <div className="patient-variants-modal__spinner"></div>
              <p>Cargando variantes...</p>
            </div>
          ) : filteredVariants.length === 0 ? (
            <div className="patient-variants-modal__empty">
              <p>No se encontraron variantes con los filtros aplicados</p>
            </div>
          ) : (
            <>
              <div className="patient-variants-modal__table-wrapper">
                <table className="patient-variants-modal__table">
                  <thead className="patient-variants-modal__table-head">
                    <tr>
                      <th>rsID</th>
                      <th>Cromosoma</th>
                      <th>Posición</th>
                      <th>Genotipo</th>
                      <th>Fenotipo</th>
                      <th>Categoría</th>
                      <th>Nivel Riesgo</th>
                      <th>Magnitud</th>
                      <th>Alelo Ref.</th>
                      <th>Alelo Alt.</th>
                    </tr>
                  </thead>
                  <tbody className="patient-variants-modal__table-body">
                    {paginatedVariants.map((variant, index) => (
                      <tr key={`${variant.rsid}-${index}`}>
                        <td className="patient-variants-modal__cell--bold">{variant.rsid || 'N/A'}</td>
                        <td>{variant.cromosoma || 'N/A'}</td>
                        <td>{variant.posicion ? variant.posicion.toLocaleString() : 'N/A'}</td>
                        <td>{variant.genotipo || 'N/A'}</td>
                        <td className="patient-variants-modal__cell--fenotipo" title={variant.fenotipo}>
                          {variant.fenotipo || 'N/A'}
                        </td>
                        <td>
                          <span className={`patient-variants-modal__badge patient-variants-modal__badge--${variant.categoria?.toLowerCase() || 'unknown'}`}>
                            {capitalize(variant.categoria) || 'N/A'}
                          </span>
                        </td>
                        <td>
                          <span className={`patient-variants-modal__risk-badge patient-variants-modal__risk-badge--${variant.nivel_riesgo?.toLowerCase() || 'unknown'}`}>
                            {variant.nivel_riesgo || 'N/A'}
                          </span>
                        </td>
                        <td>{variant.magnitud_efecto ? variant.magnitud_efecto.toFixed(2) : 'N/A'}</td>
                        <td>{variant.alelo_referencia || 'N/A'}</td>
                        <td>{variant.alelo_alternativo || 'N/A'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="patient-variants-modal__pagination">
                  <button
                    className="patient-variants-modal__pagination-btn"
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft size={18} />
                    Anterior
                  </button>

                  <div className="patient-variants-modal__pagination-info">
                    Página {currentPage} de {totalPages} • {filteredVariants.length} resultados
                  </div>

                  <button
                    className="patient-variants-modal__pagination-btn"
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    disabled={currentPage === totalPages}
                  >
                    Siguiente
                    <ChevronRight size={18} />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
