import { useState } from "react";
import { api, ApiError } from "../api.js";
import { AEROPUERTOS, hoy, precio } from "../config.js";

/**
 * Flujo del cliente: buscar -> elegir vuelo -> datos del pasajero -> confirmacion.
 * Los data-testid son el contrato con el harness (R8): no cambiar sin revisar FRONTEND.md.
 */
export default function BuscarPage() {
  const [form, setForm] = useState({ origin: "BOG", destination: "MDE", date: hoy() });
  const [estado, setEstado] = useState("idle"); // idle | cargando | ok | error
  const [vuelos, setVuelos] = useState([]);
  const [error, setError] = useState(null);

  const [elegido, setElegido] = useState(null);
  const [nombre, setNombre] = useState("");
  const [clase, setClase] = useState("ECONOMY");
  const [reservando, setReservando] = useState(false);
  const [errorReserva, setErrorReserva] = useState(null);
  const [reserva, setReserva] = useState(null);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function buscar(e) {
    e?.preventDefault();
    setElegido(null);
    setReserva(null);
    setErrorReserva(null);
    const origin = form.origin.trim().toUpperCase();
    const destination = form.destination.trim().toUpperCase();
    if (!origin || !destination || !form.date) {
      setEstado("error");
      setError("Completa origen, destino y fecha.");
      return;
    }
    setEstado("cargando");
    setError(null);
    try {
      setVuelos(await api.buscarVuelos({ origin, destination, date: form.date }));
      setEstado("ok");
    } catch (err) {
      setEstado("error");
      setError(
        err instanceof ApiError && err.status === 0
          ? "No hay conexión con el servidor."
          : "No se pudo buscar. Revisa los códigos de aeropuerto (3 letras) y la fecha."
      );
    }
  }

  function elegir(v) {
    setElegido(v);
    setErrorReserva(null);
    setReserva(null);
  }

  async function confirmar(e) {
    e?.preventDefault();
    if (!nombre.trim()) {
      setErrorReserva("Escribe el nombre del pasajero.");
      return;
    }
    setReservando(true);
    setErrorReserva(null);
    try {
      const r = await api.crearReserva({
        flight_id: elegido.flight_id,
        passenger_name: nombre.trim(),
        fare_class: clase,
      });
      setReserva(r);
      setElegido(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrorReserva("Lo sentimos: ese vuelo se quedó sin asientos. Prueba con otro.");
      } else if (err instanceof ApiError && err.status === 404) {
        setErrorReserva("El vuelo ya no existe.");
      } else {
        setErrorReserva("No se pudo completar la reserva. Intenta de nuevo.");
      }
    } finally {
      setReservando(false);
    }
  }

  function nuevaBusqueda() {
    setReserva(null);
    setNombre("");
    setVuelos([]);
    setEstado("idle");
  }

  if (reserva) {
    return (
      <div className="page">
        <section className="card confirm">
          <div className="confirm-check">✓</div>
          <h1>¡Reserva confirmada!</h1>
          <p className="hint">Guarda este código: identifica tu reserva.</p>
          <p className="codigo" data-testid="confirmation-id">{reserva.reservation_id}</p>
          <dl className="kv">
            <dt>Pasajero</dt><dd>{reserva.passenger_name}</dd>
            <dt>Vuelo</dt><dd>{reserva.flight_id}</dd>
            <dt>Estado</dt><dd><span className="badge estado-CONFIRMED">{reserva.status}</span></dd>
          </dl>
          <div className="confirm-actions">
            <button onClick={nuevaBusqueda}>Hacer otra reserva</button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Buscar vuelos</h1>

      <form className="card search-form" onSubmit={buscar}>
        <label>
          Origen
          <input data-testid="search-origin" list="aeropuertos" maxLength={3} value={form.origin}
                 onChange={set("origin")} placeholder="BOG" autoComplete="off" />
        </label>
        <label>
          Destino
          <input data-testid="search-destination" list="aeropuertos" maxLength={3} value={form.destination}
                 onChange={set("destination")} placeholder="MDE" autoComplete="off" />
        </label>
        <label>
          Fecha
          <input data-testid="search-date" type="date" value={form.date} onChange={set("date")} />
        </label>
        <button type="submit" data-testid="search-submit" disabled={estado === "cargando"}>
          {estado === "cargando" ? "Buscando…" : "Buscar"}
        </button>
        <datalist id="aeropuertos">
          {AEROPUERTOS.map((a) => <option key={a} value={a} />)}
        </datalist>
      </form>

      {error && <div className="alert error" role="alert">{error}</div>}

      {estado === "ok" && vuelos.length === 0 && (
        <div className="alert" role="status">
          No hay vuelos con cupo para esa búsqueda. Prueba otra fecha o ruta.
        </div>
      )}

      {vuelos.length > 0 && (
        <>
          <h2>Resultados</h2>
          <ul className="results">
            {vuelos.map((v) => (
              <li key={v.flight_id} className="card result" data-testid="flight-row">
                <div className="result-legs">
                  <div className="leg">
                    <strong className="itin-vuelo">{v.flight_id}</strong>
                    <span>{v.route.replace("-", " → ")}</span>
                    <span className="hint">{v.flight_date}</span>
                  </div>
                  <div className="result-meta">
                    <span className="badge">Directo</span>
                    <span className="seats">{v.seats_available} asientos disponibles</span>
                  </div>
                </div>
                <div className="result-cta">
                  <div className="price"><span>desde</span><strong>{precio(v.price_cents)}</strong></div>
                  <button data-testid="reserve-button" onClick={() => elegir(v)}>Reservar</button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {elegido && (
        <form className="card" onSubmit={confirmar}>
          <h2>Datos del pasajero</h2>
          <p className="hint">
            Vuelo {elegido.flight_id} · {elegido.route.replace("-", " → ")} · {elegido.flight_date} ·{" "}
            {precio(elegido.price_cents)}
          </p>
          <fieldset className="pax">
            <legend>Pasajero</legend>
            <label className="wide">
              Nombre completo
              <input data-testid="passenger-name" value={nombre} onChange={(e) => setNombre(e.target.value)}
                     autoFocus autoComplete="off" />
            </label>
            <label>
              Clase
              <select value={clase} onChange={(e) => setClase(e.target.value)}>
                <option value="ECONOMY">Económica</option>
                <option value="BUSINESS">Ejecutiva</option>
              </select>
            </label>
          </fieldset>
          {errorReserva && <div className="alert error" role="alert">{errorReserva}</div>}
          <div className="confirm-actions">
            <button type="button" className="ghost" onClick={() => setElegido(null)}>Cancelar</button>
            <button type="submit" data-testid="confirm-submit" disabled={reservando}>
              {reservando ? "Reservando…" : "Confirmar reserva"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
