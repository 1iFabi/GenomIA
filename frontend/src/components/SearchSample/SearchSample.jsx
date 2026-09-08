import React, { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
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
            placeholder="Buscar por SampleID..."
            value={sampleId}
            onChange={(e) => setSampleId(e.target.value)}
            className="search-sample-input"
          />
        </div>
        <button type="submit" className="search-sample-button" disabled={loading}>
          {loading ? <Loader2 className="spin" size={20} /> : 'Buscar'}
        </button>
      </form>
    </div>
  );
};

export default SearchSample;
