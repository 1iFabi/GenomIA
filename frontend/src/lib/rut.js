/** Mismo cálculo de dígito verificador que el backend (profiles.models.normalize_rut). */
export function normalizeRut(raw) {
  const rut = String(raw || "").replace(/[.\s]/g, "").toUpperCase();
  const match = /^(\d{7,8})-([\dK])$/.exec(rut);
  if (!match) return null;
  let total = 0;
  [...match[1]].reverse().forEach((digit, index) => {
    total += Number(digit) * [2, 3, 4, 5, 6, 7][index % 6];
  });
  const rest = 11 - (total % 11);
  const check = rest === 11 ? "0" : rest === 10 ? "K" : String(rest);
  return check === match[2] ? rut : null;
}
