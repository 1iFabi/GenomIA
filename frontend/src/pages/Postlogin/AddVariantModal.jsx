import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { CONTINENTS, COUNTRY_CODES, DATABASE_SOURCES, ANCESTRY_SOURCES, EVIDENCE_TYPES } from '../../constants/geneticFormOptions';
import './AddVariantModal.css';

const AddVariantModal = ({ isOpen, onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    // Basic fields
    rsid: '',
    genotipo: '',
    fenotipo: '',
    categoria: 'rasgos',
    
    // Genomic fields
    cromosoma: '',
    posicion: '',
    alelo_referencia: '',
    alelo_alternativo: '',
    
    // Clinical fields
    nivel_riesgo: 'Bajo',
    magnitud_efecto: '',
    
    // Metadata
    fuente_base_datos: '',
    tipo_evidencia: '',
    fecha_actualizacion: new Date().toISOString().split('T')[0],
    
    // Ancestry - Continent
    continente: '',
    af_continente: '',
    fuente_continente: '',
    poblacion_continente: '',
    
    // Ancestry - Country
    pais: '',
    af_pais: '',
    fuente_pais: '',
    poblacion_pais: '',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showOtherSource, setShowOtherSource] = useState(false);
  const [showOtherAncestrySource, setShowOtherAncestrySource] = useState(false);
  const [showOtherAncestrySourceCountry, setShowOtherAncestrySourceCountry] = useState(false);
  const [showOtherEvidence, setShowOtherEvidence] = useState(false);
  const [availableCountries, setAvailableCountries] = useState([]);

  // Efecto para actualizar países cuando cambia continente
  useEffect(() => {
    if (formData.continente && CONTINENTS[formData.continente]) {
      setAvailableCountries(CONTINENTS[formData.continente].countries);
    } else {
      setAvailableCountries([]);
    }
  }, [formData.continente]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    let updates = { [name]: value };

    // Lógica de autocompletado según el campo
    if (name === 'continente') {
      if (CONTINENTS[value]) {
        updates.poblacion_continente = CONTINENTS[value].code;
      }
      // Reset país cuando cambia continente
      updates.pais = '';
      updates.poblacion_pais = '';
    } else if (name === 'pais') {
      if (COUNTRY_CODES[value]) {
        updates.poblacion_pais = COUNTRY_CODES[value];
      }
    } else if (name === 'fuente_base_datos') {
      setShowOtherSource(value === 'Otra');
    } else if (name === 'fuente_continente') {
      setShowOtherAncestrySource(value === 'Otra');
    } else if (name === 'fuente_pais') {
      setShowOtherAncestrySourceCountry(value === 'Otra');
    } else if (name === 'tipo_evidencia') {
      setShowOtherEvidence(value === 'Otra');
    }

    setFormData(prev => ({
      ...prev,
      ...updates
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // Validar campos requeridos
    if (!formData.rsid || !formData.genotipo || !formData.fenotipo) {
      setError('rsID, Genotipo y Fenotipo son requeridos');
      return;
    }

    setLoading(true);
    try {
      await onSubmit(formData);
      // Reset form
      setFormData({
        rsid: '',
        genotipo: '',
        fenotipo: '',
        categoria: 'rasgos',
        cromosoma: '',
        posicion: '',
        alelo_referencia: '',
        alelo_alternativo: '',
        nivel_riesgo: 'Bajo',
        magnitud_efecto: '',
        fuente_base_datos: '',
        tipo_evidencia: '',
        fecha_actualizacion: new Date().toISOString().split('T')[0],
        continente: '',
        af_continente: '',
        fuente_continente: '',
        poblacion_continente: '',
        pais: '',
        af_pais: '',
        fuente_pais: '',
        poblacion_pais: '',
      });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="add-variant-modal-overlay" onClick={onClose}>
      <div className="add-variant-modal" onClick={(e) => e.stopPropagation()}>
        <div className="add-variant-modal__header">
          <h2>Agregar Nueva Variante Genética</h2>
          <button
            className="add-variant-modal__close"
            onClick={onClose}
            aria-label="Cerrar"
          >
            <X size={24} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="add-variant-modal__form">
          {error && (
            <div className="add-variant-modal__error">
              {error}
            </div>
          )}

          {/* SECTION 1: Información Básica */}
          <div className="add-variant-modal__section">
            <h3>Información Básica</h3>
            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>rsID *</label>
                <input
                  type="text"
                  name="rsid"
                  value={formData.rsid}
                  onChange={handleChange}
                  placeholder="ej: rs12913832"
                  required
                />
              </div>
              <div className="add-variant-modal__group">
                <label>Genotipo *</label>
                <input
                  type="text"
                  name="genotipo"
                  value={formData.genotipo}
                  onChange={handleChange}
                  placeholder="ej: CC, AC, AA"
                  required
                />
              </div>
            </div>

            <div className="add-variant-modal__group">
              <label>Fenotipo *</label>
              <textarea
                name="fenotipo"
                value={formData.fenotipo}
                onChange={handleChange}
                placeholder="Descripción del fenotipo"
                rows="3"
                required
              />
            </div>

            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>Categoría</label>
                <select
                  name="categoria"
                  value={formData.categoria}
                  onChange={handleChange}
                >
                  <option value="rasgos">Rasgos</option>
                  <option value="biometrica">Biométrica</option>
                  <option value="enfermedades">Enfermedades</option>
                  <option value="biomarcadores">Biomarcadores</option>
                  <option value="farmacogenetica">Farmacogenética</option>
                </select>
              </div>
              <div className="add-variant-modal__group">
                <label>Nivel de Riesgo</label>
                <select
                  name="nivel_riesgo"
                  value={formData.nivel_riesgo}
                  onChange={handleChange}
                >
                  <option value="Bajo">Bajo</option>
                  <option value="Intermedio">Intermedio</option>
                  <option value="Alto">Alto</option>
                  <option value="N/A">N/A</option>
                </select>
              </div>
            </div>
          </div>

          {/* SECTION 2: Información Genómica */}
          <div className="add-variant-modal__section">
            <h3>Información Genómica</h3>
            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>Cromosoma</label>
                <input
                  type="text"
                  name="cromosoma"
                  value={formData.cromosoma}
                  onChange={handleChange}
                  placeholder="ej: 1, 2, X"
                />
              </div>
              <div className="add-variant-modal__group">
                <label>Posición</label>
                <input
                  type="number"
                  name="posicion"
                  value={formData.posicion}
                  onChange={handleChange}
                  placeholder="Posición genómica"
                />
              </div>
            </div>

            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>Alelo Referencia</label>
                <input
                  type="text"
                  name="alelo_referencia"
                  value={formData.alelo_referencia}
                  onChange={handleChange}
                  placeholder="ej: A"
                />
              </div>
              <div className="add-variant-modal__group">
                <label>Alelo Alternativo</label>
                <input
                  type="text"
                  name="alelo_alternativo"
                  value={formData.alelo_alternativo}
                  onChange={handleChange}
                  placeholder="ej: G"
                />
              </div>
            </div>

            <div className="add-variant-modal__group">
              <label>Magnitud del Efecto</label>
              <input
                type="number"
                step="0.01"
                name="magnitud_efecto"
                value={formData.magnitud_efecto}
                onChange={handleChange}
                placeholder="ej: 1.25"
              />
            </div>
          </div>

          {/* SECTION 3: Metadata */}
          <div className="add-variant-modal__section">
            <h3>Metadata</h3>
            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>Fuente de Base de Datos</label>
                <select
                  name="fuente_base_datos"
                  value={formData.fuente_base_datos}
                  onChange={handleChange}
                >
                  <option value="">Seleccionar...</option>
                  {DATABASE_SOURCES.map(source => (
                    <option key={source} value={source}>{source}</option>
                  ))}
                </select>
                {showOtherSource && (
                  <input
                    type="text"
                    placeholder="Especificar fuente"
                    value={formData.fuente_base_datos === 'Otra' ? '' : formData.fuente_base_datos}
                    onChange={(e) => setFormData(prev => ({ ...prev, fuente_base_datos: e.target.value }))}
                    className="add-variant-modal__input-other"
                  />
                )}
              </div>
              <div className="add-variant-modal__group">
                <label>Tipo de Evidencia</label>
                <select
                  name="tipo_evidencia"
                  value={formData.tipo_evidencia}
                  onChange={handleChange}
                >
                  <option value="">Seleccionar...</option>
                  {EVIDENCE_TYPES.map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
                {showOtherEvidence && (
                  <input
                    type="text"
                    placeholder="Especificar tipo de evidencia"
                    value={formData.tipo_evidencia === 'Otra' ? '' : formData.tipo_evidencia}
                    onChange={(e) => setFormData(prev => ({ ...prev, tipo_evidencia: e.target.value }))}
                    className="add-variant-modal__input-other"
                  />
                )}
              </div>
            </div>

            <div className="add-variant-modal__group">
              <label>Fecha de Actualización</label>
              <input
                type="date"
                name="fecha_actualizacion"
                value={formData.fecha_actualizacion}
                onChange={handleChange}
              />
            </div>
          </div>

          {/* SECTION 4: Datos de Ancestría - Continente */}
          <div className="add-variant-modal__section">
            <h3>Ancestría - Continente</h3>
            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>Continente</label>
                <select
                  name="continente"
                  value={formData.continente}
                  onChange={handleChange}
                >
                  <option value="">Seleccionar...</option>
                  {Object.keys(CONTINENTS).map(continent => (
                    <option key={continent} value={continent}>{continent}</option>
                  ))}
                </select>
              </div>
              <div className="add-variant-modal__group">
                <label>Frecuencia Alélica</label>
                <input
                  type="number"
                  step="0.0001"
                  name="af_continente"
                  value={formData.af_continente}
                  onChange={handleChange}
                  placeholder="0.0000 - 1.0000"
                  min="0"
                  max="1"
                />
              </div>
            </div>

            <div className="add-variant-modal__grid-2">
              <div className="add-variant-modal__group">
                <label>Fuente</label>
                <select
                  name="fuente_continente"
                  value={formData.fuente_continente}
                  onChange={handleChange}
                >
                  <option value="">Seleccionar...</option>
                  {ANCESTRY_SOURCES.map(source => (
                    <option key={source} value={source}>{source}</option>
                  ))}
                </select>
                {showOtherAncestrySource && (
                  <input
                    type="text"
                    placeholder="Especificar fuente"
                    value={formData.fuente_continente === 'Otra' ? '' : formData.fuente_continente}
                    onChange={(e) => setFormData(prev => ({ ...prev, fuente_continente: e.target.value }))}
                    className="add-variant-modal__input-other"
                  />
                )}
              </div>
              <div className="add-variant-modal__group">
                <label>Población (autocompletado)</label>
                <input
                  type="text"
                  name="poblacion_continente"
                  value={formData.poblacion_continente}
                  onChange={handleChange}
                  placeholder="ej: EUR, AFR"
                  title="Se rellena automáticamente pero se puede editar"
                />
              </div>
            </div>
          </div>

          {/* SECTION 5: Datos de Ancestría - País */}
          <div className="add-variant-modal__section">
            <h3>Ancestría - País</h3>
            {formData.continente ? (
              <>
                <div className="add-variant-modal__grid-2">
                  <div className="add-variant-modal__group">
                    <label>País de {formData.continente}</label>
                    <select
                      name="pais"
                      value={formData.pais}
                      onChange={handleChange}
                    >
                      <option value="">Seleccionar...</option>
                      {availableCountries.map(country => (
                        <option key={country} value={country}>{country}</option>
                      ))}
                    </select>
                  </div>
                  <div className="add-variant-modal__group">
                    <label>Frecuencia Alélica</label>
                    <input
                      type="number"
                      step="0.0001"
                      name="af_pais"
                      value={formData.af_pais}
                      onChange={handleChange}
                      placeholder="0.0000 - 1.0000"
                      min="0"
                      max="1"
                    />
                  </div>
                </div>

                <div className="add-variant-modal__grid-2">
                  <div className="add-variant-modal__group">
                    <label>Fuente</label>
                    <select
                      name="fuente_pais"
                      value={formData.fuente_pais}
                      onChange={handleChange}
                    >
                      <option value="">Seleccionar...</option>
                      {ANCESTRY_SOURCES.map(source => (
                        <option key={source} value={source}>{source}</option>
                      ))}
                    </select>
                    {showOtherAncestrySourceCountry && (
                      <input
                        type="text"
                        placeholder="Especificar fuente"
                        value={formData.fuente_pais === 'Otra' ? '' : formData.fuente_pais}
                        onChange={(e) => setFormData(prev => ({ ...prev, fuente_pais: e.target.value }))}
                        className="add-variant-modal__input-other"
                      />
                    )}
                  </div>
                  <div className="add-variant-modal__group">
                    <label>Población (autocompletado)</label>
                    <input
                      type="text"
                      name="poblacion_pais"
                      value={formData.poblacion_pais}
                      onChange={handleChange}
                      placeholder="ej: IBS"
                      title="Se rellena automáticamente pero se puede editar"
                    />
                  </div>
                </div>
              </>
            ) : (
              <div className="add-variant-modal__info-message">
                <p>🚫 Selecciona primero un continente en la sección anterior</p>
              </div>
            )}
          </div>

          {/* Form Actions */}
          <div className="add-variant-modal__actions">
            <button
              type="button"
              className="add-variant-modal__btn-cancel"
              onClick={onClose}
              disabled={loading}
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="add-variant-modal__btn-submit"
              disabled={loading}
            >
              {loading ? 'Guardando...' : 'Agregar Variante'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddVariantModal;
