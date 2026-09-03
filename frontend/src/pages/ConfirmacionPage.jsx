import { useLocation, useNavigate, Navigate, Link } from "react-router-dom";
import { useConfig, useFormatters } from "../config.jsx";
import { makeT } from "../i18n/index.js";

export default function ConfirmacionPage() {
  const { locale } = useConfig();
  const t = makeT(locale);
  const fmt = useFormatters();
  const navigate = useNavigate();
  const { state } = useLocation();

  if (!state?.reserva) return <Navigate to="/buscar" replace />;
  const { reserva } = state;

  return (
    <div className="page">
      <div className="card confirm">
        <div className="confirm-check">✓</div>
        <h1>{t("confirm.titulo")}</h1>

        <dl className="kv">
          <dt>{t("confirm.codigo")}</dt>
          <dd className="codigo">{reserva.codigo_reserva}</dd>

          <dt>{t("confirm.estado")}</dt>
          <dd>
            <span className={`badge estado-${reserva.estado}`}>
              {t(`estado.${reserva.estado}`)}
            </span>
          </dd>

          {reserva.retenida_hasta && (
            <>
              <dt>{t("confirm.retenidaHasta")}</dt>
              <dd>{fmt.dateTime(reserva.retenida_hasta)}</dd>
            </>
          )}

          <dt>{t("confirm.total")}</dt>
          <dd>
            <strong>{fmt.money(reserva.monto_total, reserva.moneda)}</strong>
          </dd>
        </dl>

        {reserva.retenida_hasta && (
          <p className="hint">{t("confirm.holdNota")}</p>
        )}

        <div className="confirm-actions">
          <Link
            className="btn"
            to={`/mi-reserva/${reserva.codigo_reserva}`}
          >
            {t("confirm.verReserva")}
          </Link>
          <button className="btn ghost" onClick={() => navigate("/buscar")}>
            {t("confirm.nuevaBusqueda")}
          </button>
        </div>
      </div>
    </div>
  );
}
