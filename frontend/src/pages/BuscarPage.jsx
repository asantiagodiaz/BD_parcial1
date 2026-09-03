import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api.js";
import { useConfig, useFormatters } from "../config.jsx";
import { makeT } from "../i18n/index.js";

const AEROPUERTOS = ["BOG", "MDE", "CTG", "CLO", "BAQ"];
const CABINAS = ["ECONOMICA", "EJECUTIVA"];

function hoyMas(dias) {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

export default function BuscarPage() {
  const { locale } = useConfig();
  const t = makeT(locale);
  const fmt = useFormatters();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    origin: "BOG",
    dest: "MDE",
    date: hoyMas(7),
    pax: 1,
    cabin: "ECONOMICA",
    withStops: true,
  });
  const [estado, setEstado] = useState("idle"); // idle | cargando | ok | error
  const [opciones, setOpciones] = useState([]);
  const [error, setError] = useState(null);

  const set = (k) => (e) => {
    const v =
      e.target.type === "checkbox"
        ? e.target.checked
        : e.target.type === "number"
        ? Number(e.target.value)
        : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  async function buscar(e) {
    e?.preventDefault();
    setEstado("cargando");
    setError(null);
    try {
      const r = await api.buscarVuelos(form);
      setOpciones(r.opciones || []);
      setEstado("ok");
    } catch (err) {
      setEstado("error");
      setError(
        err instanceof ApiError && err.status === 0
          ? t("error.red")
          : t("error.generico")
      );
    }
  }

  function elegir(opcion) {
    // se pasa la opcion elegida + los datos de busqueda a la pantalla de seleccion
    navigate("/seleccion", { state: { opcion, form } });
  }

  return (
    <div className="page">
      <h1>{t("nav.buscar")}</h1>

      <form className="card search-form" onSubmit={buscar}>
        <label>
          {t("search.origen")}
          <select value={form.origin} onChange={set("origin")}>
            {AEROPUERTOS.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          {t("search.destino")}
          <select value={form.dest} onChange={set("dest")}>
            {AEROPUERTOS.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          {t("search.fecha")}
          <input type="date" value={form.date} onChange={set("date")} />
        </label>
        <label>
          {t("search.pasajeros")}
          <input
            type="number"
            min="1"
            max="9"
            value={form.pax}
            onChange={set("pax")}
          />
        </label>
        <label>
          {t("search.cabina")}
          <select value={form.cabin} onChange={set("cabin")}>
            {CABINAS.map((c) => (
              <option key={c} value={c}>
                {t(`cabina.${c}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.withStops}
            onChange={set("withStops")}
          />
          {t("search.conEscalas")}
        </label>
        <button type="submit" disabled={estado === "cargando"}>
          {estado === "cargando" ? t("search.buscando") : t("search.buscar")}
        </button>
      </form>

      <p className="hint">{t("search.aeropuertosDemo")}</p>

      {error && <div className="alert error">{error}</div>}

      {estado === "ok" && opciones.length === 0 && (
        <div className="alert">{t("search.sinResultados")}</div>
      )}

      {opciones.length > 0 && (
        <section>
          <h2>{t("results.titulo")}</h2>
          <ul className="results">
            {opciones.map((op, i) => (
              <li key={i} className="card result">
                <div className="result-legs">
                  {op.tramos.map((tr, j) => (
                    <div key={j} className="leg">
                      <div className="leg-time">
                        <strong>{fmt.time(tr.salida_utc)}</strong>
                        <span>{tr.iata_origen}</span>
                      </div>
                      <div className="leg-arrow">
                        <span>{tr.numero_vuelo}</span>
                        <span className="line" />
                      </div>
                      <div className="leg-time">
                        <strong>{fmt.time(tr.llegada_utc)}</strong>
                        <span>{tr.iata_destino}</span>
                      </div>
                      {j === 0 && op.escalas > 0 && (
                        <div className="leg-stop">
                          {t("results.escalaEn", {
                            a: op.tramos[0].iata_destino,
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <div className="result-meta">
                  <span className="badge">
                    {op.escalas === 0
                      ? t("results.directo")
                      : t("results.unaEscala")}
                  </span>
                  <span className="seats">
                    {t("results.asientosLibres", {
                      n: Math.min(
                        ...op.tramos.map((x) => x.asientos_disponibles)
                      ),
                    })}
                  </span>
                  <span className="fare">
                    {op.tramos[0].tarifa.clase_tarifa}
                  </span>
                </div>
                <div className="result-cta">
                  <div className="price">
                    <span>{t("results.total")}</span>
                    <strong>{fmt.money(op.precio_total, op.moneda)}</strong>
                  </div>
                  <button onClick={() => elegir(op)}>
                    {t("results.seleccionar")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
