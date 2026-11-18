import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { porcentaje } from "../config.js";

const VENTANAS = [5, 15, 60];

/**
 * Panel gerencial del parcial 3. Muestra los dos caminos de los datos:
 *   1. Camino rapido: /analytics/live (lo alimenta el consumidor de Kinesis), se actualiza
 *      cada 3 s y cuenta por la hora del evento.
 *   2. Camino analitico: el modelo estrella en Athena se reconstruye por micro-lotes; aqui
 *      se puede lanzar el refresco y ver su estado.
 */
export default function ManagerPage() {
  const [ventana, setVentana] = useState(5);
  const [vivo, setVivo] = useState(null);
  const [errorVivo, setErrorVivo] = useState(false);
  const [actualizado, setActualizado] = useState(null);
  const [estrella, setEstrella] = useState(null);
  const sondeo = useRef(null);

  useEffect(() => {
    let activo = true;
    async function cargar() {
      try {
        const d = await api.enVivo(ventana);
        if (!activo) return;
        setVivo(d);
        setErrorVivo(false);
        setActualizado(new Date());
      } catch {
        if (activo) setErrorVivo(true);
      }
    }
    cargar();
    const t = setInterval(cargar, 3000);
    return () => { activo = false; clearInterval(t); };
  }, [ventana]);

  useEffect(() => {
    api.estadoEstrella().then(setEstrella).catch(() => {});
    return () => clearInterval(sondeo.current);
  }, []);

  async function refrescar() {
    try {
      await api.refrescarEstrella();
      setEstrella({ state: "RUNNING" });
      clearInterval(sondeo.current);
      sondeo.current = setInterval(async () => {
        const s = await api.estadoEstrella().catch(() => null);
        if (!s) return;
        setEstrella(s);
        if (s.state !== "RUNNING") clearInterval(sondeo.current);
      }, 5000);
    } catch {
      setEstrella({ state: "FAILED", error: "no se pudo iniciar el refresco" });
    }
  }

  const corriendo = estrella?.state === "RUNNING";

  return (
    <div className="page">
      <h1>Panel gerencial</h1>
      <p className="hint">
        Actividad de los últimos minutos, leída directamente del stream de eventos (Kinesis).
        Cuenta por la hora en que ocurrió cada evento, no por la hora en que llegó.
      </p>

      <div className="tabs" role="tablist" aria-label="Ventana de tiempo">
        {VENTANAS.map((v) => (
          <button key={v} role="tab" aria-selected={v === ventana}
                  className={v === ventana ? "" : "ghost"} onClick={() => setVentana(v)}>
            Últimos {v} min
          </button>
        ))}
      </div>

      {errorVivo && <div className="alert error" role="alert">No se pudo leer la vista en vivo. Reintentando…</div>}

      <section className="kpi-grid" aria-live="polite">
        <Kpi titulo="Búsquedas" valor={vivo?.searches} testid="live-searches" />
        <Kpi titulo="Reservas" valor={vivo?.reservations} testid="live-reservations" />
        <Kpi titulo="Cancelaciones" valor={vivo?.cancellations} testid="live-cancellations" />
        <Kpi titulo="Conversión" valor={vivo ? porcentaje(vivo.conversion) : undefined} testid="live-conversion"
             nota="reservas / búsquedas" />
      </section>
      <p className="hint small">
        {actualizado ? `Actualizado ${actualizado.toLocaleTimeString("es-CO")} · se refresca cada 3 s` : "Cargando…"}
      </p>

      <section className="card">
        <h2>Modelo estrella (Athena)</h2>
        <p className="hint">
          El análisis histórico (ingresos por mes, rutas, festivos, puentes) se consulta en Athena sobre
          un modelo estrella que se reconstruye cada pocos minutos desde la landing zone en S3.
        </p>
        <div className="confirm-actions">
          <button onClick={refrescar} disabled={corriendo} data-testid="refresh-star">
            {corriendo ? "Reconstruyendo…" : "Reconstruir ahora"}
          </button>
          {estrella && (
            <span className={`badge estado-${estrella.state}`} data-testid="refresh-state">{estrella.state}</span>
          )}
        </div>
        {estrella?.finished_at && !corriendo && (
          <dl className="kv">
            <dt>Última corrida</dt><dd>{new Date(estrella.finished_at).toLocaleString("es-CO")}</dd>
            {estrella.seconds != null && <><dt>Duración</dt><dd>{estrella.seconds} s</dd></>}
            {estrella.bytes_scanned != null && (
              <><dt>Datos escaneados</dt><dd>{(estrella.bytes_scanned / 1e6).toFixed(1)} MB</dd></>
            )}
            {estrella.error && <><dt>Error</dt><dd>{estrella.error}</dd></>}
          </dl>
        )}
      </section>
    </div>
  );
}

function Kpi({ titulo, valor, testid, nota }) {
  return (
    <div className="card kpi">
      <p className="kpi-title">{titulo}</p>
      <p className="kpi-value" data-testid={testid}>
        {valor === undefined ? "—" : typeof valor === "number" ? valor.toLocaleString("es-CO") : valor}
      </p>
      {nota && <p className="kpi-label">{nota}</p>}
    </div>
  );
}
