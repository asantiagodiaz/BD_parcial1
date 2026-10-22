/** Cliente de la API (mismo origen: la sirve el mismo backend). */
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
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
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
    request(`/flights/search?${new URLSearchParams({ origin, destination, date })}`),

  crearReserva: (payload) =>
    request("/reservations", { method: "POST", body: JSON.stringify(payload) }),

  ocupacion: (route, month) =>
    request(`/analytics/occupancy?${new URLSearchParams({ route, month })}`),
};
