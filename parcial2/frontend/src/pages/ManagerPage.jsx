import { useState } from "react";
import { api, ApiError } from "../api.js";
import { RUTAS, porcentaje } from "../config.js";

/**
 * Panel gerencial. Responde dos preguntas:
 *   1. como le fue a UNA ruta en UN mes (tarjeta grande, endpoint /analytics/occupancy)
 *   2. que rutas llenan mas sus aviones ese mes (ranking de las 9 rutas del equipo)
 *
 * La tarjeta se muestra apenas llega su valor; el ranking se completa despues pidiendo
 * las otras rutas en paralelo (cada una es una consulta real a Athena).
 * Los data-testid son el contrato con el harness (R9).
 */
export default function ManagerPage() {
  const [route, setRoute] = useState("");
  const [month, setMonth] = useState("");
  const [estado, setEstado] = useState("idle"); // idle | cargando | ok | vacio | error
  const [dato, setDato] = useState(null);
  const [error, setError] = useState(null);
  const [ranking, setRanking] = useState(null); // null = no pedido; [] = cargando/vacio
  const [cargandoRanking, setCargandoRanking] = useState(false);

  async function cargar(e) {
    e?.preventDefault();
    const r = route.trim().toUpperCase();
    const m = month.trim();
    setDato(null);
    setRanking(null);
    setError(null);

    if (!/^[A-Z]{3}-[A-Z]{3}$/.test(r) || !/^\d{4}-(0[1-9]|1[0-2])$/.test(m)) {
      setEstado("error");
      setError("Usa una ruta como BOG-MDE y un mes como 2024-03.");
      return;
    }

    setEstado("cargando");
    try {
      const d = await api.ocupacion(r, m);
      setDato(d);
      setEstado("ok");
      cargarRanking(r, m, d);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setEstado("vacio");
      } else {
        setEstado("error");
        setError("No se pudo consultar la ocupación. Intenta de nuevo en unos segundos.");
      }
    }
  }

  async function cargarRanking(r, m, principal) {
    setCargandoRanking(true);
    const otras = RUTAS.filter((x) => x !== r);
    // en paralelo; las rutas sin datos en ese mes (404) simplemente no aparecen
    const res = await Promise.allSettled(otras.map((x) => api.ocupacion(x, m)));
    const filas = [principal];
    res.forEach((p) => p.status === "fulfilled" && filas.push(p.value));
    filas.sort((a, b) => b.occupancy - a.occupancy);
    setRanking({ mes: m, ruta: r, filas });
    setCargandoRanking(false);
  }

  return (
    <div className="page">
      <h1>Panel gerencial</h1>
      <p className="hint">
        Consulta cuántos asientos se vendieron y qué tan llenos van los aviones por ruta y mes.
        Los datos vienen del historial de 2 años, procesado con EMR y consultado con Athena.
      </p>

      <form className="card search-form" onSubmit={cargar}>
        <label>
          Ruta
          <input data-testid="manager-route" list="rutas" value={route} onChange={(e) => setRoute(e.target.value)}
                 placeholder="SMR-BAQ" autoComplete="off" />
        </label>
        <label>
          Mes (AAAA-MM)
          <input data-testid="manager-month" value={month} onChange={(e) => setMonth(e.target.value)}
                 placeholder="2024-01" maxLength={7} autoComplete="off" />
        </label>
        <button type="submit" data-testid="manager-load" disabled={estado === "cargando"}>
          {estado === "cargando" ? "Consultando…" : "Consultar"}
        </button>
        <datalist id="rutas">
          {RUTAS.map((x) => <option key={x} value={x} />)}
        </datalist>
      </form>

      {error && <div className="alert error" role="alert">{error}</div>}
      {estado === "vacio" && (
        <div className="alert" role="status">No hay datos para esa ruta y mes. Rutas con datos: {RUTAS.join(", ")}.</div>
      )}

      {dato && (
        <section className="card kpi">
          <p className="kpi-title">{dato.route.replace("-", " → ")} · {dato.month}</p>
          <p className="kpi-value" data-testid="occupancy-value">{porcentaje(dato.occupancy)}</p>
          <p className="kpi-label">de ocupación</p>
          <div className="bar big"><span style={{ width: `${Math.min(dato.occupancy * 100, 100)}%` }} /></div>
          <dl className="kv kpi-detail">
            <dt>Asientos vendidos</dt><dd>{dato.seats_sold.toLocaleString("es-CO")}</dd>
            <dt>Capacidad del mes</dt><dd>{dato.seats_capacity.toLocaleString("es-CO")}</dd>
          </dl>
        </section>
      )}

      {dato && (
        <section className="card">
          <h2>Ocupación por ruta en {dato.month}</h2>
          {cargandoRanking && !ranking && <p className="hint">Comparando las 9 rutas…</p>}
          {ranking && (
            <ol className="ranking">
              {ranking.filas.map((f, i) => (
                <li key={f.route} className={f.route === ranking.ruta ? "actual" : ""}>
                  <span className="pos">{i + 1}</span>
                  <span className="ruta">{f.route.replace("-", " → ")}</span>
                  <div className="bar"><span style={{ width: `${Math.min(f.occupancy * 100, 100)}%` }} /></div>
                  <span className="pct">{porcentaje(f.occupancy)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
