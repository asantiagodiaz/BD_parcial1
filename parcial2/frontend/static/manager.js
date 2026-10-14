// Panel gerencial: consulta /analytics/occupancy (que a su vez consulta Athena).
const $ = (id) => document.getElementById(id);

async function cargar() {
  const route = $("manager-route").value.trim().toUpperCase();
  const month = $("manager-month").value.trim();
  const msg = $("manager-msg");
  $("result").hidden = true;

  if (!/^[A-Z]{3}-[A-Z]{3}$/.test(route) || !/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) {
    msg.textContent = "Usa una ruta como BOG-MDE y un mes como 2024-03.";
    return;
  }
  msg.textContent = "Consultando...";
  try {
    const qs = new URLSearchParams({ route, month });
    const res = await fetch(`/analytics/occupancy?${qs}`);
    if (res.status === 404) {
      msg.textContent = "No hay datos para esa ruta y mes.";
      return;
    }
    if (!res.ok) throw new Error(`error ${res.status}`);
    const d = await res.json();
    msg.textContent = "";
    // 2 decimales: el error de redondeo (<= 0.005 %) queda muy por debajo de la tolerancia
    $("occupancy-value").textContent = `${(d.occupancy * 100).toFixed(2)}%`;
    $("occupancy-detail").textContent =
      `${d.route} · ${d.month}: ${d.seats_sold.toLocaleString("es-CO")} asientos vendidos de ` +
      `${d.seats_capacity.toLocaleString("es-CO")}`;
    $("result").hidden = false;
  } catch (e) {
    msg.textContent = `No se pudo consultar: ${e.message}`;
  }
}

$("manager-load").addEventListener("click", cargar);
