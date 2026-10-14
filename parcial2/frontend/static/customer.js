// Flujo del cliente: buscar -> reservar -> confirmacion. JS plano, sin build.
// La API vive en el mismo origen (la sirve el mismo backend).
const $ = (id) => document.getElementById(id);
const tid = (name) => document.querySelector(`[data-testid="${name}"]`);

let selectedFlight = null;

async function buscar() {
  const origin = tid("search-origin").value.trim().toUpperCase();
  const destination = tid("search-destination").value.trim().toUpperCase();
  const date = tid("search-date").value.trim();
  const msg = $("search-msg");
  const list = $("results");
  list.innerHTML = "";
  $("booking").hidden = true;
  $("confirmation").hidden = true;

  if (!origin || !destination || !date) {
    msg.textContent = "Completa origen, destino y fecha.";
    return;
  }
  msg.textContent = "Buscando...";
  try {
    const qs = new URLSearchParams({ origin, destination, date });
    const res = await fetch(`/flights/search?${qs}`);
    if (!res.ok) throw new Error(`error ${res.status}`);
    const flights = await res.json();
    msg.textContent = flights.length ? "" : "No hay vuelos con cupo para esa búsqueda.";
    for (const f of flights) list.appendChild(filaVuelo(f));
  } catch (e) {
    msg.textContent = `No se pudo buscar: ${e.message}`;
  }
}

function filaVuelo(f) {
  const li = document.createElement("li");
  li.setAttribute("data-testid", "flight-row");
  const precio = (f.price_cents / 100).toLocaleString("es-CO", { style: "currency", currency: "COP" });
  const info = document.createElement("span");
  info.textContent = `${f.flight_id} · ${f.route} · ${f.flight_date}`;
  const det = document.createElement("span");
  det.textContent = `${f.seats_available} asientos · ${precio}`;
  li.append(info, det);
  const btn = document.createElement("button");
  btn.textContent = "Reservar";
  btn.setAttribute("data-testid", "reserve-button");
  btn.addEventListener("click", () => elegir(f));
  li.appendChild(btn);
  return li;
}

function elegir(f) {
  selectedFlight = f;
  $("booking-flight").textContent = f.flight_id;
  $("booking-msg").textContent = "";
  $("confirmation").hidden = true;
  $("booking").hidden = false;
  $("passenger-name").focus();
}

async function confirmar() {
  const name = $("passenger-name").value.trim();
  const msg = $("booking-msg");
  if (!name) {
    msg.textContent = "Escribe el nombre del pasajero.";
    return;
  }
  $("confirm-submit").disabled = true;
  msg.textContent = "Reservando...";
  try {
    const res = await fetch("/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        flight_id: selectedFlight.flight_id,
        passenger_name: name,
        fare_class: $("fare-class").value,
      }),
    });
    if (res.status === 409) {
      msg.textContent = "Lo sentimos, ese vuelo se quedó sin asientos.";
      return;
    }
    if (!res.ok) throw new Error(`error ${res.status}`);
    const body = await res.json();
    msg.textContent = "";
    $("confirmation-id").textContent = body.reservation_id;
    $("booking").hidden = true;
    $("confirmation").hidden = false;
  } catch (e) {
    msg.textContent = `No se pudo reservar: ${e.message}`;
  } finally {
    $("confirm-submit").disabled = false;
  }
}

tid("search-submit").addEventListener("click", buscar);
$("confirm-submit").addEventListener("click", confirmar);
