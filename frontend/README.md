# Frontend — SPA de reservas (5.5)

Single-Page Application en **React + Vite** que consume la API REST del backend
(5.4). Implementa el alcance del MVP definido en
[`docs/05-arquitectura-frontend.md`](../docs/05-arquitectura-frontend.md):

**búsqueda → selección + datos de pasajeros → confirmación (hold) → código**
y **consultar reserva**.

## Estructura

| Archivo | Rol |
|---|---|
| `src/api.js` | cliente HTTP de la API; `ApiError` con status para el manejo del 409/404/red |
| `src/config.jsx` | contexto global `locale`/`currency` + formateadores `Intl` (5.5.4) |
| `src/i18n/es-CO.json` + `index.js` | textos externalizados; ningún literal en componentes (5.5.4) |
| `src/pages/BuscarPage.jsx` | buscador + resultados (`GET /flights/search`) — FR-01/02/03 |
| `src/pages/SeleccionPage.jsx` | itinerario + pasajeros + canal; polling de disponibilidad cada 15 s (5.5.2); `POST /reservations` |
| `src/pages/ConfirmacionPage.jsx` | código de reserva, estado, hold |
| `src/pages/MiReservaPage.jsx` | `GET /reservations/{codigo}` con historial — FR-12 |

**Manejo del 409 (5.5.2):** si `POST /reservations` devuelve 409, la SPA muestra
*"Ese vuelo se acaba de agotar…"* y vuelve al buscador. La disponibilidad en la
pantalla de selección es orientativa (polling best-effort); la garantía es el
409 + la transacción del backend.

## Ejecutar en local

```bash
cd frontend
npm install
cp .env.example .env      # deja VITE_API_URL vacio para usar el proxy a localhost:8000
npm run dev               # http://localhost:5173
```

Necesita el backend corriendo en `localhost:8000` (ver `backend/README.md`).

## Apuntar a la API en AWS

```bash
# IP publica actual de la EC2 (cambia al reiniciar el Lab):
IP=$(AWS_PROFILE=academy aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=aerolinea-api" "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text)

echo "VITE_API_URL=http://$IP:8000" > .env
npm run dev
```

El backend ya envía cabeceras CORS (`app/main.py`, configurable con
`CORS_ORIGINS` en `backend/.env`).

## Build de producción

```bash
npm run build        # genera dist/
npm run preview      # sirve dist/ en http://localhost:4173 para revisar
```

`dist/` es estático: se puede servir desde cualquier servidor de estáticos o
desde un bucket S3 configurado como sitio web.
