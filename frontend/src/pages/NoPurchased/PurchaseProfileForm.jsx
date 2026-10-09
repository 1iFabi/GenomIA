import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_ENDPOINTS, apiRequest, refreshSession } from "../../config/api";
import { normalizeRut } from "../../lib/rut";

const CURRENT_YEAR = new Date().getFullYear();
const MIN_YEAR = 1900;
const YEAR_DIGITS = 4;
const RUT_MAX_LENGTH = 10; // "12345678-K"
const NAME_MAX_LENGTH = 30;
const PHONE_DIGITS = 8;
const SEX_OPTIONS = [
  ["female", "Femenino"],
  ["male", "Masculino"],
  ["other", "Otro"],
];

const validate = (form) => {
  const errors = {};
  if (!form.nombre.trim()) errors.nombre = "Ingresa tus nombres";
  else if (form.nombre.trim().length > NAME_MAX_LENGTH) errors.nombre = `Máximo ${NAME_MAX_LENGTH} caracteres`;
  if (!form.apellido.trim()) errors.apellido = "Ingresa tus apellidos";
  else if (form.apellido.trim().length > NAME_MAX_LENGTH) errors.apellido = `Máximo ${NAME_MAX_LENGTH} caracteres`;
  if (!/^\d{7,8}-[\dK]$/.test(form.rut)) errors.rut = "Escribe tu RUT sin puntos y con guion (ej: 12345678-5)";
  else if (!normalizeRut(form.rut)) errors.rut = "Revisa tu RUT: el dígito verificador no coincide";
  if (form.telefono.length !== PHONE_DIGITS) errors.telefono = `Ingresa los ${PHONE_DIGITS} dígitos después de +569`;
  if (!form.sexoAlNacer) errors.sexoAlNacer = "Selecciona una opción";
  const year = Number(form.anioNacimiento);
  if (form.anioNacimiento.length !== YEAR_DIGITS || year < MIN_YEAR || year > CURRENT_YEAR) {
    errors.anioNacimiento = `Escribe un año entre ${MIN_YEAR} y ${CURRENT_YEAR}`;
  }
  return errors;
};

const cleanValue = (name, value) => {
  if (name === "rut") return value.toUpperCase().replace(/[^0-9K-]/g, "").slice(0, RUT_MAX_LENGTH);
  if (name === "telefono") return value.replace(/\D/g, "").slice(0, PHONE_DIGITS);
  if (name === "anioNacimiento") return value.replace(/\D/g, "").slice(0, YEAR_DIGITS);
  if (name === "nombre" || name === "apellido") return value.slice(0, NAME_MAX_LENGTH);
  return value;
};

/**
 * Datos que se piden recién al iniciar la compra (no en el registro): identifican al cliente
 * en recepción y emiten su Sample ID.
 */
export default function PurchaseProfileForm({ user }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    nombre: (user?.first_name || "").slice(0, NAME_MAX_LENGTH),
    apellido: (user?.last_name || "").slice(0, NAME_MAX_LENGTH),
    rut: "",
    telefono: "",
    sexoAlNacer: "",
    anioNacimiento: "",
  });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);

  const setValue = (name, value) => {
    setForm((previous) => ({ ...previous, [name]: cleanValue(name, value) }));
    setErrors((previous) => ({ ...previous, [name]: undefined }));
  };
  const update = (event) => setValue(event.target.name, event.target.value);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length) {
      event.currentTarget.querySelector(`[name="${Object.keys(found)[0]}"], #purchase-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    setLoading(true);
    setServerError("");
    const { ok, data } = await apiRequest(API_ENDPOINTS.PURCHASE_PROFILE, {
      method: "POST",
      body: JSON.stringify({
        nombre: form.nombre.trim(),
        apellido: form.apellido.trim(),
        rut: normalizeRut(form.rut),
        telefono: `+569${form.telefono}`,
        sexoAlNacer: form.sexoAlNacer,
        anioNacimiento: Number(form.anioNacimiento),
      }),
    });
    setLoading(false);
    if (ok) {
      refreshSession(); // /me trae purchase_profile_complete y el Sample ID.
      navigate("/", {
        replace: true,
        state: { purchaseEmail: { sent: data?.emailSent !== false, email: user?.email || "" } },
      });
    } else if (data?.rut_exists) {
      setErrors({ rut: data.error });
    } else {
      setServerError(data?.error || "No pudimos guardar tus datos. Inténtalo nuevamente.");
    }
  };

  const errorId = (name) => (errors[name] ? `purchase-${name}-error` : undefined);
  const field = (name, label, input) => (
    <div className={`purchase-field${errors[name] ? " purchase-field--error" : ""}`}>
      <label htmlFor={`purchase-${name}`}>{label}</label>
      {input}
      {errors[name] && <span id={`purchase-${name}-error`} className="purchase-field__error">{errors[name]}</span>}
    </div>
  );
  const inputProps = (name) => ({
    id: `purchase-${name}`,
    name,
    value: form[name],
    onChange: update,
    "aria-invalid": !!errors[name],
    "aria-describedby": errorId(name),
  });

  return (
    <form className="purchase-form" onSubmit={handleSubmit} noValidate>
      <p className="purchase-intro">
        Para comprar tu examen necesitamos identificarte. Estos datos solo los usa recepción para
        verificar tu identidad y el laboratorio para tu análisis.
      </p>
      <div className="purchase-grid">
        {field("nombre", "Nombres", (
          <input {...inputProps("nombre")} maxLength={NAME_MAX_LENGTH} autoComplete="given-name" placeholder="María José" />
        ))}
        {field("apellido", "Apellidos", (
          <input {...inputProps("apellido")} maxLength={NAME_MAX_LENGTH} autoComplete="family-name" placeholder="González Pérez" />
        ))}
        {field("rut", "RUT", (
          <input
            {...inputProps("rut")}
            maxLength={RUT_MAX_LENGTH}
            inputMode="text"
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            placeholder="12345678-5"
          />
        ))}
        {field("telefono", "Teléfono", (
          <div className="purchase-phone">
            <span aria-hidden="true">+569</span>
            <input
              {...inputProps("telefono")}
              type="tel"
              inputMode="numeric"
              autoComplete="tel-local"
              maxLength={PHONE_DIGITS}
              placeholder="12345678"
            />
          </div>
        ))}
        {field("sexoAlNacer", "Sexo", (
          <select {...inputProps("sexoAlNacer")}>
            <option value="">Selecciona…</option>
            {SEX_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        ))}
        {field("anioNacimiento", "Año de nacimiento", (
          <input
            {...inputProps("anioNacimiento")}
            inputMode="numeric"
            autoComplete="bday-year"
            maxLength={YEAR_DIGITS}
            placeholder="1990"
          />
        ))}
      </div>
      {serverError && <p className="purchase-server-error" role="alert">{serverError}</p>}
      <button type="submit" className="purchase-submit" disabled={loading}>
        {loading ? "Guardando…" : "Continuar con la compra"}
      </button>
    </form>
  );
}
