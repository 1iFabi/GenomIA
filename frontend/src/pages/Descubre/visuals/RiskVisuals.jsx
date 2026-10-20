// an illustrative stretch of DNA, not a real BRCA2 read; the middle row carries the one changed letter
const ROWS = ["GATTCAGCTAGGCTTA", "ACCTGAGTCTACGGAT", "TTGACCATGCAGTCAG"];
const VARIANT = { row: 1, at: 9, was: "C", is: "T" };

/**
 * The monogenic reading as type: rows of DNA letters, all as everyone has them except one.
 */
export function VariantLetters() {
  return (
    <figure className="risk-letters" aria-label="Filas de letras del ADN donde una sola letra es distinta.">
      {ROWS.map((row, r) => (
        <p key={row} className="risk-letters__row" aria-hidden="true">
          {[...row].map((letter, i) =>
            r === VARIANT.row && i === VARIANT.at
              ? <b key={i} className="risk-letters__variant" title={`${VARIANT.was} → ${VARIANT.is}`}>{VARIANT.is}</b>
              : <span key={i}>{letter}</span>,
          )}
        </p>
      ))}
    </figure>
  );
}
