/**
 * Cliente de la API REST del backend (5.4).
 *
 * Base URL:
 *  - VITE_API_URL si esta definida (p. ej. http://<IP-EC2>:8000 contra AWS)
 *  - si no, "/api" -> proxy de Vite a localhost:8000 en desarrollo
 */
const BASE = import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "/api";

/** Error de negocio de la API: lleva el status HTTP y el cuerpo. */
export class ApiError extends Error {
  constructor(status, body) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (e) {
    // fallo de red / CORS / servidor caido
    throw new ApiError(0, { detail: String(e) });
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export const api = {
  health: () => request("/health"),

  // FR-01/02/03
  buscarVuelos: ({ origin, dest, date, pax, cabin, withStops }) => {
    const q = new URLSearchParams({
      origin,
      dest,
      date,
      pax: String(pax),
      cabin,
      with_stops: String(withStops),
    });
    return request(`/flights/search?${q}`);
  },

  // NFR-03 - contador orientativo para el polling
  disponibilidad: (idInstancia, cabin) =>
    request(
      `/flights/${idInstancia}/availability?cabin=${encodeURIComponent(cabin)}`
    ),

  // FR-04/05/06 - puede lanzar ApiError(409) si el asiento se agoto
  crearReserva: (payload) =>
    request("/reservations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // FR-12
  consultarReserva: (codigo) =>
    request(`/reservations/${encodeURIComponent(codigo)}`),
};

export { BASE as API_BASE };
