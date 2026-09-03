import { useEffect, useState, useCallback } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { api, ApiError } from "../api.js";
import { useConfig, useFormatters } from "../config.jsx";
import { makeT } from "../i18n/index.js";

const TIPOS_DOC = ["CC", "CE", "PP", "TI"];
const POLL_MS = 15000; // 5.5.2 - polling ligero

function pasajeroVacio(principal = false) {
  return {
    tipo_documento: "CC",
    numero_documento: "",
    nombre_completo: "",
    correo: "",
    telefono: "",
    es_contacto_principal: principal,
  };
}

export default function SeleccionPage() {
  const { locale } = useConfig();
  const t = makeT(locale);
  const fmt = useFormatters();
  const navigate = useNavigate();
  const { state } = useLocation();

  if (!state?.opcion) return <Navigate to="/buscar" replace />;
  const { opcion, form } = state;

  const [pasajeros, setPasajeros] = useState(() =>
    Array.from({ length: form.pax }, (_, i) => pasajeroVacio(i === 0))
  );
  const [canal, setCanal] = useState("DIRECTO");
  const [idAgencia, setIdAgencia] = useState("");
  const [dispon, setDispon] = useState({}); // idInstancia -> asientos
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  // 5.5.2 - polling de disponibilidad orientativa mientras el usuario decide
  const refrescarDisponibilidad = useCallback(async () => {
    const entradas = await Promise.all(
      opcion.tramos.map(async (tr) => {
        try {
          const d = await api.disponibilidad(tr.id_instancia_vuelo, tr.cabina);
          return [tr.id_instancia_vuelo, d.asientos_disponibles];
        } catch {
          return [tr.id_instancia_vuelo, null];
        }
      })
    );
    setDispon(Object.fromEntries(entradas));
  }, [opcion]);

  useEffect(() => {
    refrescarDisponibilidad();
    const id = setInterval(refrescarDisponibilidad, POLL_MS);
    return () => clearInterval(id);
  }, [refrescarDisponibilidad]);

  const setPax = (i, k) => (e) => {
    const v =
      e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setPasajeros((ps) =>
      ps.map((p, j) => {
        if (j !== i) {
          // solo un contacto principal
          return k === "es_contacto_principal" && v
            ? { ...p, es_contacto_principal: false }
            : p;
        }
        return { ...p, [k]: v };
      })
    );
  };

  async function confirmar(e) {
    e.preventDefault();
    setEnviando(true);
    setError(null);

    const payload = {
      canal,
      id_agencia: canal === "AGENCIA" && idAgencia ? Number(idAgencia) : null,
      segmentos: opcion.tramos.map((tr) => ({
        id_instancia_vuelo: tr.id_instancia_vuelo,
        cabina: tr.cabina,
        id_tarifa: tr.tarifa.id_tarifa,
      })),
      pasajeros: pasajeros.map((p) => ({
        ...p,
        correo: p.correo || null,
        telefono: p.telefono || null,
      })),
    };

    try {
      const r = await api.crearReserva(payload);
      navigate("/confirmacion", { state: { reserva: r, opcion } });
    } catch (err) {
      setEnviando(false);
      if (err instanceof ApiError && err.status === 409) {
        // 5.5.2 - el asiento se agoto: avisar y volver a buscar
        setError(t("error.agotado"));
        setTimeout(
          () => navigate("/buscar", { state: { rebuscar: form } }),
          1800
        );
      } else if (err instanceof ApiError && err.status === 0) {
        setError(t("error.red"));
      } else if (err instanceof ApiError && err.status === 422) {
        setError(t("error.generico") + " (datos incompletos)");
      } else {
        setError(t("error.generico"));
      }
    }
  }

  return (
    <div className="page">
      <button className="link-back" onClick={() => navigate(-1)}>
        ← {t("select.volver")}
      </button>
      <h1>{t("select.titulo")}</h1>

      <section className="card">
        <h2>{t("select.itinerario")}</h2>
        <ul className="itin">
          {opcion.tramos.map((tr, i) => (
            <li key={i}>
              <span className="itin-vuelo">{tr.numero_vuelo}</span>
              <span>
                {tr.iata_origen} {fmt.time(tr.salida_utc)} →{" "}
                {tr.iata_destino} {fmt.time(tr.llegada_utc)}
              </span>
              <span className="itin-cabina">{t(`cabina.${tr.cabina}`)}</span>
              <span className="itin-disp">
                {t("select.disponibilidad")}:{" "}
                <strong>
                  {dispon[tr.id_instancia_vuelo] ?? "…"}
                </strong>
              </span>
            </li>
          ))}
        </ul>
        <p className="hint">{t("select.disponibilidadNota")}</p>
        <div className="total-row">
          <span>{t("results.total")}</span>
          <strong>{fmt.money(opcion.precio_total, opcion.moneda)}</strong>
        </div>
      </section>

      <form className="card" onSubmit={confirmar}>
        {pasajeros.map((p, i) => (
          <fieldset key={i} className="pax">
            <legend>{t("select.pasajero", { n: i + 1 })}</legend>
            <label>
              {t("select.tipoDoc")}
              <select
                value={p.tipo_documento}
                onChange={setPax(i, "tipo_documento")}
              >
                {TIPOS_DOC.map((d) => (
                  <option key={d} value={d}>
                    {t(`doc.${d}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("select.numDoc")}
              <input
                required
                value={p.numero_documento}
                onChange={setPax(i, "numero_documento")}
              />
            </label>
            <label className="wide">
              {t("select.nombre")}
              <input
                required
                value={p.nombre_completo}
                onChange={setPax(i, "nombre_completo")}
              />
            </label>
            <label>
              {t("select.correo")}
              <input
                type="email"
                value={p.correo}
                onChange={setPax(i, "correo")}
              />
            </label>
            <label>
              {t("select.telefono")}
              <input value={p.telefono} onChange={setPax(i, "telefono")} />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={p.es_contacto_principal}
                onChange={setPax(i, "es_contacto_principal")}
              />
              {t("select.contactoPrincipal")}
            </label>
          </fieldset>
        ))}

        <fieldset className="pax">
          <legend>{t("select.canal")}</legend>
          <label>
            {t("select.canal")}
            <select value={canal} onChange={(e) => setCanal(e.target.value)}>
              <option value="DIRECTO">{t("select.canalDirecto")}</option>
              <option value="AGENCIA">{t("select.canalAgencia")}</option>
            </select>
          </label>
          {canal === "AGENCIA" && (
            <label>
              {t("select.idAgencia")}
              <input
                type="number"
                value={idAgencia}
                onChange={(e) => setIdAgencia(e.target.value)}
              />
            </label>
          )}
        </fieldset>

        {error && <div className="alert error">{error}</div>}

        <button type="submit" disabled={enviando}>
          {enviando ? t("select.confirmando") : t("select.confirmar")}
        </button>
      </form>
    </div>
  );
}
