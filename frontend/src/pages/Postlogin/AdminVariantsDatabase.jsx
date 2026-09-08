import React, { useState, useEffect, useMemo } from 'react';
import { Search, Plus, Menu, X, Database, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import AdminSidebar from '../../components/AdminSidebar/AdminSidebar';
import AddVariantModal from './AddVariantModal';
import './AdminVariantsDatabase.css';

const AdminVariantsDatabase = ({ user }) => {
  const navigate = useNavigate();
  const [variants, setVariants] = useState([]);
  const [filteredVariants, setFilteredVariants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('todos');
  const [currentPage, setCurrentPage] = useState(1);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [sortBy, setSortBy] = useState('id');
  const [sortOrder, setSortOrder] = useState('asc');

  const itemsPerPage = 10;

  // Función para capitalizar primera letra
  const capitalize = (str) => {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  };

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) {
        setIsMobileMenuOpen(false);
      }
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Fetch variants from API
  useEffect(() => {
    const fetchVariants = async () => {
      try {
        setLoading(true);
        setError(null);
        console.log('🔄 Fetching variants from:', API_ENDPOINTS.VARIANTS);
        const response = await apiRequest(API_ENDPOINTS.VARIANTS, { method: 'GET' });
        
        console.log('📡 API Response:', {
          ok: response.ok,
          status: response.status,
          data: response.data,
          hasData: !!response.data.data,
          dataLength: Array.isArray(response.data.data) ? response.data.data.length : 'N/A'
        });

        if (response.ok && response.data && response.data.data && Array.isArray(response.data.data)) {
          console.log('✅ Variants loaded successfully:', response.data.data.length);
          setVariants(response.data.data);
        } else {
          console.error('❌ Invalid response structure:', response);
          setError(`No se pudieron cargar las variantes. Status: ${response.status}`);
          setVariants([]);
        }
      } catch (err) {
        console.error('❌ Error fetching variants:', err);
        setError(`Error al conectar con el servidor: ${err.message}`);
        setVariants([]);
      } finally {
        setLoading(false);
      }
    };

    fetchVariants();
  }, []);

  // Filter variants based on search and category
  useEffect(() => {
    let filtered = variants;

    if (categoryFilter !== 'todos') {
      filtered = filtered.filter(v => v.categoria === categoryFilter);
    }

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(v =>
        (v.rsid?.toLowerCase().includes(term)) ||
        (v.fenotipo?.toLowerCase().includes(term)) ||
        (v.cromosoma?.toLowerCase().includes(term)) ||
        (v.pais?.toLowerCase().includes(term))
      );
    }

    // Apply sorting
    filtered = [...filtered].sort((a, b) => {
      let aValue = a[sortBy];
      let bValue = b[sortBy];

      // Handle null/undefined values
      if (aValue == null) aValue = '';
      if (bValue == null) bValue = '';

      // Convert to numbers if the field contains numbers
      if (sortBy === 'posicion' || sortBy === 'magnitud_efecto' || sortBy === 'af_continente' || sortBy === 'af_pais') {
        aValue = parseFloat(aValue) || 0;
        bValue = parseFloat(bValue) || 0;
      }

      // Convert to strings for comparison if not numbers
      if (typeof aValue === 'string') aValue = aValue.toLowerCase();
      if (typeof bValue === 'string') bValue = bValue.toLowerCase();

      if (aValue < bValue) return sortOrder === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

    setFilteredVariants(filtered);
    setCurrentPage(1);
  }, [searchTerm, categoryFilter, variants, sortBy, sortOrder]);

  // Get unique categories
  const categories = useMemo(() => {
    const cats = new Set(variants.map(v => v.categoria).filter(Boolean));
    return Array.from(cats).sort();
  }, [variants]);

  // Pagination
  const totalPages = Math.ceil(filteredVariants.length / itemsPerPage);
  const startIdx = (currentPage - 1) * itemsPerPage;
  const paginatedVariants = filteredVariants.slice(startIdx, startIdx + itemsPerPage);

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (error) {
      console.error('Error al cerrar sesión', error);
    }
    clearToken();
    navigate('/');
  };

  const getRiskColor = (nivel) => {
    const nivel_lower = nivel?.toLowerCase() || '';
    if (nivel_lower.includes('alto')) return '#EF4444';
    if (nivel_lower.includes('intermedio')) return '#F59E0B';
    if (nivel_lower.includes('bajo')) return '#10B981';
    return '#6B7A90';
  };

  const getCategoryColor = (categoria) => {
    const colors = {
      'rasgos': '#3B82F6',
      'biometrica': '#EC4899',
      'enfermedades': '#EF4444',
      'biomarcadores': '#10B981',
      'farmacogenetica': '#F59E0B'
    };
    return colors[categoria] || '#6B7A90';
  };

  const handleAddVariant = async (formData) => {
    try {
      console.log('📝 Adding new variant:', formData);
      
      // Llamada POST al backend
      const response = await apiRequest(API_ENDPOINTS.VARIANTS, { 
        method: 'POST', 
        body: JSON.stringify(formData),
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      console.log('📡 POST Response:', response);
      
      if (response.ok && response.data.success) {
        // Recargar la lista completa desde el servidor
        const refreshResponse = await apiRequest(API_ENDPOINTS.VARIANTS, { method: 'GET' });
        if (refreshResponse.ok && refreshResponse.data.data) {
          setVariants(refreshResponse.data.data);
        }
        console.log('✅ Variante agregada exitosamente con ID:', response.data.data.id);
      } else {
        throw new Error(response.data.error || 'Error desconocido del servidor');
      }
    } catch (err) {
      console.error('Error adding variant:', err);
      throw new Error('Error al agregar variante: ' + err.message);
    }
  };

  const isAdmin = user?.is_staff || user?.is_superuser || user?.roles?.includes('ADMIN');

  return (
    <div className="admin-variants-wrapper">
      {isMobile && (
        <button 
          className="admin-variants__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      )}

      <aside className="admin-variants__sidebar">
        <AdminSidebar 
          onLogout={handleLogout} 
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
          isAdmin={isAdmin}
        />
      </aside>

      <main className="admin-variants__main">
        {/* Header */}
        <div className="admin-variants__header">
          <div className="admin-variants__headline">
            <h1 className="admin-variants__title">Base de Datos de Variantes Genéticas</h1>
            <p className="admin-variants__subtitle">
              Gestiona y visualiza todas las variantes genéticas disponibles en el sistema
            </p>
          </div>
          <button 
            className="admin-variants__btn-add"
            onClick={() => setIsAddModalOpen(true)}
          >
            <Plus size={20} />
            Agregar Variante
          </button>
        </div>

        {/* Stats */}
        <div className="admin-variants__stats-container">
          <div className="admin-variants__stat">
            <span className="admin-variants__stat-label">Total variantes</span>
            <span className="admin-variants__stat-value">{variants.length}</span>
          </div>
          <div className="admin-variants__stat">
            <span className="admin-variants__stat-label">Mostrando</span>
            <span className="admin-variants__stat-value">{paginatedVariants.length}</span>
          </div>
          {categoryFilter !== 'todos' && (
            <div className="admin-variants__stat">
              <span className="admin-variants__stat-label">Categoría filtro</span>
              <span className="admin-variants__stat-value">{capitalize(categoryFilter)}</span>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="admin-variants__controls">
          <div className="admin-variants__search">
            <Search size={18} />
            <input
              type="text"
              placeholder="Buscar por rsID, fenotipo, cromosoma o país..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="admin-variants__search-input"
            />
          </div>

          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="admin-variants__filter"
          >
            <option value="todos">Todas las categorías</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{capitalize(cat)}</option>
            ))}
          </select>

          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="admin-variants__filter"
            title="Ordenar por"
          >
            <option value="id">ID</option>
            <option value="rsid">rsID</option>
            <option value="cromosoma">Cromosoma</option>
            <option value="posicion">Posición</option>
            <option value="categoria">Categoría</option>
            <option value="magnitud_efecto">Magnitud</option>
            <option value="nivel_riesgo">Nivel Riesgo</option>
            <option value="fenotipo">Fenotipo</option>
          </select>

          <button
            onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
            className="admin-variants__sort-toggle"
            title={sortOrder === 'asc' ? 'Descendente' : 'Ascendente'}
          >
            {sortOrder === 'asc' ? '↑' : '↓'}
          </button>
        </div>

        {/* Table */}
        {loading ? (
          <div className="admin-variants__loading">
            <div className="admin-variants__spinner"></div>
            <p>Cargando variantes...</p>
          </div>
        ) : error ? (
          <div className="admin-variants__error">
            <p>{error}</p>
          </div>
        ) : paginatedVariants.length === 0 ? (
          <div className="admin-variants__empty">
            <Database size={40} />
            <p>No se encontraron variantes</p>
          </div>
        ) : (
          <div className="admin-variants__table-container">
            <table className="admin-variants__table">
              <thead>
                <tr>
                  <th>rsID</th>
                  <th>Genotipo</th>
                  <th>Fenotipo</th>
                  <th>Categoría</th>
                  <th>Magnitud</th>
                  <th>Nivel Riesgo</th>
                  <th>Fuente</th>
                  <th>Actualización</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {paginatedVariants.map((variant) => (
                  <React.Fragment key={variant.id}>
                    <tr 
                      className={`cursor-pointer ${expandedRow === variant.id ? 'expanded' : ''}`}
                      onClick={() => setExpandedRow(expandedRow === variant.id ? null : variant.id)}
                    >
                      <td data-label="rsID" className="admin-variants__rsid">{variant.rsid}</td>
                      <td data-label="Genotipo" className="admin-variants__genotipo">{variant.genotipo}</td>
                      <td data-label="Fenotipo" className="admin-variants__fenotipo" title={variant.fenotipo}>
                        {variant.fenotipo?.substring(0, 40)}...
                      </td>
                      <td data-label="Categoría">
                        <span 
                          className="admin-variants__badge"
                          style={{ backgroundColor: `${getCategoryColor(variant.categoria)}20`, color: getCategoryColor(variant.categoria) }}
                        >
                          {capitalize(variant.categoria)}
                        </span>
                      </td>
                      <td data-label="Magnitud">{variant.magnitud_efecto || '-'}</td>
                      <td data-label="Nivel Riesgo">
                        <span 
                          className="admin-variants__risk"
                          style={{ backgroundColor: `${getRiskColor(variant.nivel_riesgo)}20`, color: getRiskColor(variant.nivel_riesgo) }}
                        >
                          {variant.nivel_riesgo}
                        </span>
                      </td>
                      <td data-label="Fuente" className="admin-variants__source">{variant.fuente_base_datos || '-'}</td>
                      <td data-label="Actualización">{variant.fecha_actualizacion || '-'}</td>
                      <td data-label="Acciones" className="admin-variants__actions">
                        <button
                          className="admin-variants__btn-action"
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedRow(expandedRow === variant.id ? null : variant.id);
                          }}
                          title="Ver detalles"
                        >
                          <Eye size={16} />
                        </button>
                      </td>
                    </tr>
                    {expandedRow === variant.id && (
                      <tr className="admin-variants__expanded-row">
                        <td colSpan="9">
                          <div className="admin-variants__details">
                            <div className="admin-variants__detail-section">
                              <h4>Información Básica</h4>
                              <div className="admin-variants__detail-full-width">
                                <span className="admin-variants__detail-label">Fenotipo</span>
                                <span className="admin-variants__detail-full-text">{variant.fenotipo}</span>
                              </div>
                            </div>

                            <div className="admin-variants__detail-section">
                              <h4>Información Genómica</h4>
                              <div className="admin-variants__detail-grid">
                                <div>
                                  <span className="admin-variants__detail-label">Alelo Referencia</span>
                                  <span>{variant.alelo_referencia}</span>
                                </div>
                                <div>
                                  <span className="admin-variants__detail-label">Alelo Alternativo</span>
                                  <span>{variant.alelo_alternativo}</span>
                                </div>
                                <div>
                                  <span className="admin-variants__detail-label">Cromosoma</span>
                                  <span>{variant.cromosoma}</span>
                                </div>
                                <div>
                                  <span className="admin-variants__detail-label">Posición</span>
                                  <span>{variant.posicion?.toLocaleString()}</span>
                                </div>
                              </div>
                            </div>

                            {(variant.continente || variant.pais) && (
                              <div className="admin-variants__detail-section">
                                <h4>Datos de Ancestría</h4>
                                <div className="admin-variants__detail-grid">
                                  {variant.continente && (
                                    <>
                                      <div>
                                        <span className="admin-variants__detail-label">Continente</span>
                                        <span>{variant.continente}</span>
                                      </div>
                                      <div>
                                        <span className="admin-variants__detail-label">AF Continente</span>
                                        <span>{variant.af_continente}</span>
                                      </div>
                                    </>
                                  )}
                                  {variant.pais && (
                                    <>
                                      <div>
                                        <span className="admin-variants__detail-label">País</span>
                                        <span>{variant.pais}</span>
                                      </div>
                                      <div>
                                        <span className="admin-variants__detail-label">AF País</span>
                                        <span>{variant.af_pais}</span>
                                      </div>
                                    </>
                                  )}
                                </div>
                              </div>
                            )}

                            <div className="admin-variants__detail-section">
                              <h4>Metadata</h4>
                              <div className="admin-variants__detail-grid">
                                <div>
                                  <span className="admin-variants__detail-label">Fuente</span>
                                  <span>{variant.fuente_base_datos}</span>
                                </div>
                                <div>
                                  <span className="admin-variants__detail-label">Tipo Evidencia</span>
                                  <span>{variant.tipo_evidencia}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="admin-variants__pagination">
            <button
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
              className="admin-variants__page-btn"
              title="Primera página"
            >
              Inicio
            </button>

            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="admin-variants__page-btn"
            >
              ← Anterior
            </button>

            <div className="admin-variants__page-info">
              Página {currentPage} de {totalPages}
            </div>

            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="admin-variants__page-btn"
            >
              Siguiente →
            </button>

            <button
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
              className="admin-variants__page-btn"
              title="Última página"
            >
              Fin
            </button>
          </div>
        )}
      </main>

      {/* Add Variant Modal */}
      <AddVariantModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSubmit={handleAddVariant}
      />
    </div>
  );
};

export default AdminVariantsDatabase;
