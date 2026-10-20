import React from 'react';
import { Search } from 'lucide-react';
import ModuleTitle from '../../components/ModuleTitle/ModuleTitle';
import ResultsBar from '../../components/ResultsBar/ResultsBar';
import './Farmacogenetica.css';

export const PGX_TITLE = 'Tus remedios';

const Bar = ({ className = '', width }) => (
  <span className={`pgx-skel ${className}`.trim()} style={width ? { '--w': width } : undefined} />
);

// Placeholder widths follow real medication names, their uses and verdicts, so the table keeps its rhythm.
const ROWS = [['46%', '30%', '62%'], ['40%', '38%', '62%'], ['52%', '30%', '62%'], ['44%', '46%', '70%'],
  ['50%', '42%', '70%'], ['38%', '30%', '54%'], ['48%', '52%', '54%'], ['42%', '36%', '54%']];

/**
 * The page while its results load, built from the page's own classes: the fixed words are real
 * text, only the data (the counts, the rows) waits as shapes. It sits exactly where the content
 * lands, so nothing moves when the results arrive.
 */
export const PgxLoadingContent = ({ label = 'Cargando datos…' }) => (
  <section className="pgx-loading" role="status" aria-live="polite" aria-busy="true">
    <span className="pgx-sr">{label}</span>
    <div aria-hidden="true">
      <p className="pgx-hero__lede"><Bar width="100%" /><Bar width="55%" /></p>
      <div className="pgx-pbar pgx-pbar--ghost">
        {[7, 8, 20].map((n) => <span key={n} className="pgx-pbar__seg" style={{ flexGrow: n }}><i /><Bar width="2.5rem" /></span>)}
      </div>
      <div className="pgx-table">
        <div className="pgx-table__bar">
          <span className="pgx-search"><Search size={17} /><span className="pgx-search__ghost">Buscar remedio</span></span>
        </div>
        <table>
          <thead>
            <tr><th><span className="pgx-th">Remedio</span></th><th className="pgx-wide"><span className="pgx-th">Gen</span></th>
              <th className="pgx-wide"><span className="pgx-th">Tu gen</span></th><th><span className="pgx-th">Efecto en ti</span></th><th className="pgx-chev" /></tr>
          </thead>
          <tbody>
            {ROWS.map(([name, use, verdict]) => (
              <tr key={name + use + verdict} className="pgx-row pgx-row--ghost">
                <td><Bar className="pgx-skel--name" width={name} /><Bar width={use} /></td>
                <td className="pgx-wide"><Bar width="60%" /></td>
                <td className="pgx-wide"><Bar width="80%" /></td>
                <td><Bar width={verdict} /></td>
                <td className="pgx-chev" />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  </section>
);

/** The whole page while the session or the page itself loads: the real bar, title and page shape. */
export const FarmacoPageSkeleton = () => (
  <div className="farmacogenetica-layout-new">
    <main className="farmaco-main-content">
      <ResultsBar />
      <div className="pgx">
        <header className="pgx-hero"><ModuleTitle className="pgx-title" moduleKey="pharmacogenetics" title={PGX_TITLE} /></header>
        <PgxLoadingContent />
      </div>
    </main>
  </div>
);
