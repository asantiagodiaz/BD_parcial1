import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api.js";
import { useConfig, useFormatters } from "../config.jsx";
import { makeT } from "../i18n/index.js";

export default function MiReservaPage() {
  const { locale } = useConfig();
  const t = makeT(locale);
  const fmt = useFormatters();
  const navigate = useNavigate();
  const { codigo: codigoUrl } = useParams();

  const [codigo, setCodigo] = useState(codigoUrl || "");
  const [reserva, setReserva] = useState(null);
  const [estado, setEstado] = useState("idle"); // idle | cargando | ok | error
  const [error, setError] = useState(null);

  async function cargar(cod) {
    setEstado("cargando");
    setError(null);
    setReserva(null);
    try {
      const r = await api.consultarReserva(cod.trim().toUpperCase());
      setReserva(r);
      setEstado("ok");
    } catch (err) {
      setEstado("error");
      if (err instanceof ApiError && err.status === 404) {
        setError(t("lookup.noEncontrada"));
      } else if (err instanceof ApiError && err.status === 0) {
        setError(t("error.red"));
      } else {
        setError(t("error.generico"));
      }
    }
  }

  useEffect(() => {
    if (codigoUrl) cargar(codigoUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codigoUrl]);

  function submit(e) {
    e.preventDefault();
    if (codigo.trim()) navigate(`/mi-reserva/${codigo.trim().toUpperCase()}`);
  }

  return (
    <div className="page">
      <h1>{t("lookup.titulo")}</h1>

      <form className="card lookup" onSubmit={submit}>
        <label>
          {t("lookup.codigo")}
          <input
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            placeholder="ABC123"
            maxLength={8}
            autoFocus
          />
        </label>
        <button type="submit" disabled={estado === "cargando"}>
          {t("lookup.buscar")}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}

      {reserva && (
        <article className="card reserva">
          <header className="reserva-head">
            <h2>{t("reserva.titulo", { codigo: reserva.codigo_reserva })}</h2>
            <span className={`badge estado-${reserva.estado}`}>
              {t(`estado.${reserva.estado}`)}
            </span>
          </header>

          <dl className="kv">
            <dt>{t("reserva.ruta")}</dt>
            <dd>
              {reserva.iata_origen} → {reserva.iata_destino}
            </dd>
            <dt>{t("reserva.canal")}</dt>
            <dd>{reserva.canal}</dd>
            <dt>{t("reserva.creada")}</dt>
            <dd>{fmt.dateTime(reserva.creada_en)}</dd>
            {reserva.retenida_hasta && (
              <>
                <dt>{t("reserva.retenidaHasta")}</dt>
                <dd>{fmt.dateTime(reserva.retenida_hasta)}</dd>
              </>
            )}
            <dt>{t("reserva.total")}</dt>
            <dd>
              <strong>
                {fmt.money(reserva.monto_total, reserva.moneda)}
              </strong>
            </dd>
            {reserva.monto_comision > 0 && (
              <>
                <dt>{t("reserva.comision")}</dt>
                <dd>{fmt.money(reserva.monto_comision, reserva.moneda)}</dd>
              </>
            )}
          </dl>

          <h3>{t("reserva.segmentos")}</h3>
          <ul className="itin">
            {reserva.segmentos.map((s) => (
              <li key={s.secuencia}>
                <span className="itin-vuelo">{s.numero_vuelo}</span>
                <span>
                  {s.iata_origen} {fmt.time(s.salida_utc)} → {s.iata_destino}{" "}
                  {fmt.time(s.llegada_utc)}
                </span>
                <span className="itin-cabina">{t(`cabina.${s.cabina}`)}</span>
                <span>{fmt.money(s.monto_segmento, reserva.moneda)}</span>
              </li>
            ))}
          </ul>

          <h3>{t("reserva.pasajeros")}</h3>
          <ul className="plain">
            {reserva.pasajeros.map((p, i) => (
              <li key={i}>
                {p.nombre_completo} · {p.tipo_documento} {p.numero_documento}
                {p.es_contacto_principal && " ★"}
              </li>
            ))}
          </ul>

          <h3>{t("reserva.pagos")}</h3>
          {reserva.pagos.length === 0 ? (
            <p className="hint">{t("reserva.sinPagos")}</p>
          ) : (
            <ul className="plain">
              {reserva.pagos.map((pg, i) => (
                <li key={i}>
                  {pg.proveedor} · {pg.estado} ·{" "}
                  {fmt.money(pg.monto, pg.moneda)}
                </li>
              ))}
            </ul>
          )}

          <h3>{t("reserva.historial")}</h3>
          <ol className="timeline">
            {reserva.historial.map((h, i) => (
              <li key={i}>
                <span className="tl-when">{fmt.dateTime(h.ocurrido_en)}</span>
                <span className="tl-what">
                  {h.tipo_evento} · {h.tipo_actor}
                </span>
              </li>
            ))}
          </ol>
        </article>
      )}
    </div>
  );
}
