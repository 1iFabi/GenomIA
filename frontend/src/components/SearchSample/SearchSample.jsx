import React, { useState } from 'react';
import { Search } from 'lucide-react';
import './SearchSample.css';

const SearchSample = ({ onSearch, loading }) => {
  const [sampleId, setSampleId] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onSearch(sampleId);
  };

  return (
    <div className="search-sample-container">
      <form onSubmit={handleSubmit} className="search-sample-form">
        <div className="search-sample-input-wrapper">
          <Search size={20} className="search-sample-icon" />
          <input
            type="text"
            placeholder="Buscar por Sample ID..."
            value={sampleId}
            onChange={(e) => setSampleId(e.target.value)}
            className="search-sample-input"
          />
        </div>
        <button type="submit" className="search-sample-button" disabled={loading}>
          Buscar
        </button>
      </form>
      {loading && <span className="search-sample-status" role="status">Buscando muestra…</span>}
    </div>
  );
};

export default SearchSample;
