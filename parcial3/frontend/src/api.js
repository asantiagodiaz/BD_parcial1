/** Cliente de la API (mismo origen: la sirve el mismo backend). */
export class ApiError extends Error {
  constructor(status, body) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

// Una sesion por pestaña: el backend la pone en el evento search_performed (clave de
// particion de Kinesis). Es un identificador aleatorio, no un dato personal.
const SESSION_ID = (() => {
  try {
    let s = sessionStorage.getItem("session_id");
    if (!s) {
      s = crypto.randomUUID();
      sessionStorage.setItem("session_id", s);
    }
    return s;
  } catch {
    return crypto.randomUUID();
  }
})();

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch (e) {
    throw new ApiError(0, { detail: String(e) });
  }
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { detail: text }; }
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export const api = {
  buscarVuelos: ({ origin, destination, date }) =>
    request(`/flights/search?${new URLSearchParams({ origin, destination, date })}`, {
      headers: { "X-Session-Id": SESSION_ID },
    }),

  crearReserva: (payload) =>
    request("/reservations", { method: "POST", body: JSON.stringify(payload) }),

  cancelarReserva: (id) =>
    request(`/reservations/${encodeURIComponent(id)}/cancel`, { method: "POST" }),

  enVivo: (window) => request(`/analytics/live?${new URLSearchParams({ window })}`),

  refrescarEstrella: () => request("/admin/refresh-star", { method: "POST" }),

  estadoEstrella: () => request("/admin/refresh-status"),
};
