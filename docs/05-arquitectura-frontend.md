# 5.5 Arquitectura del frontend

> Diagrama editable: [diagrams/05-arquitectura-frontend.drawio](diagrams/05-arquitectura-frontend.drawio).
> Cada decisión cita el requisito que la origina — FR en [01-requisitos-funcionales.md](01-requisitos-funcionales.md), NFR en [02-requisitos-no-funcionales.md](02-requisitos-no-funcionales.md).

## 5.5.1 SPA vs. renderizado en servidor

**Decisión: Single-Page Application (SPA)** — React + Vite, servida como estático
(S3 website / o local para la demo), que consume la API REST del backend (5.4).

**Justificación (trazable a NFR).**

- **NFR-01 / NFR-02 (rendimiento de búsqueda: p95 < 800 ms directos, < 1.5 s con
  escalas).** La búsqueda de vuelos es **interactiva y exploratoria**: el pasajero
  cambia fechas, filtra por cabina, compara tarifas. Con SSR cada uno de esos
  cambios sería un round-trip completo con re-render de HTML en el servidor. Con
  SPA, la primera carga trae la aplicación y luego cada búsqueda es **una llamada
  JSON**: se aprovecha mejor el presupuesto de latencia del NFR y el servidor solo
  hace el trabajo de datos, no de presentación.
- **Coste de servidor.** El backend (monolito, un `t3.micro` en el Learner Lab) no
  gasta CPU renderizando vistas; se dedica a las operaciones de negocio y a
  proteger el inventario bajo lock.
- **Separación de responsabilidades / trazabilidad.** El mismo backend sirve a
  cuatro tipos de interfaz (pasajero, agente, aeropuerto, admin — §0.3). Una SPA
  por rol contra una API común evita duplicar lógica de presentación en el servidor.

**Alternativa considerada:** SSR (Next.js server-rendered / plantillas Jinja).
Descartada por lo anterior. Nota: para SEO de páginas de destino de rutas (marketing)
se podría añadir prerender estático de esas páginas concretas; fuera del alcance del MVP.

## 5.5.2 Notificación en tiempo real de "asiento ya no disponible" (NFR-03)

**Problema del enunciado:** el usuario está en la pantalla de selección y, mientras
decide, otro pasajero compra el último asiento.

**Decisión: revalidación al confirmar + re-consulta ligera, sin WebSocket en el MVP.**

1. La disponibilidad mostrada en resultados/selección es **orientativa** (viene de
   la búsqueda, que no toma lock — 5.4.3).
2. Al pulsar **"Reservar"**, el frontend llama `POST /reservations`. Si el backend
   —que sí toma `FOR UPDATE`— detecta que ya no hay asientos, responde **HTTP 409**.
3. La SPA captura el 409 y muestra un mensaje claro *"Ese vuelo se acaba de agotar
   en la cabina seleccionada"*, y **vuelve a ejecutar la búsqueda** para refrescar
   opciones. El usuario nunca llega a un estado de sobreventa (NFR-03).
4. Mientras el usuario está en la pantalla de selección, la SPA hace un **polling
   ligero** (cada ~15 s) a un endpoint `GET /flights/{id}/availability` para
   actualizar el contador visible. Es *best-effort*: reduce sorpresas, no garantiza
   nada (la garantía es el 409 + la transacción del backend).

**Por qué no WebSocket / SSE en el MVP:** empujar cambios de inventario en tiempo
real a todos los clientes que miran un vuelo exige mantener conexiones abiertas y
publicar eventos desde `booking` en cada cambio de inventario — infraestructura
(pub/sub, gestión de conexiones) difícil de justificar en el Learner Lab para el
volumen de una aerolínea regional (S9). Se documenta como evolución: si el negocio
lo pide, `booking` publica `inventario_cambiado` y la SPA se suscribe por SSE.

## 5.5.3 Interfaz para agentes de agencia (FR-11, S3)

**Decisión: misma SPA, vista condicionada por rol** (no una aplicación separada).

- Tras autenticarse, si `rol = AGENTE_AGENCIA` la SPA habilita:
  - un paso extra para **identificar al pasajero** a nombre de quien se reserva;
  - la visualización del **descuento de agencia** aplicado y de la **comisión**
    estimada;
  - acceso a "mis reservas de la agencia".
- El **flujo de reserva es el mismo** (misma llamada `POST /reservations`), lo que
  mantiene una sola ruta de código y una sola prueba de concurrencia. Coherente con
  la decisión de backend de 5.4.5.
- Una interfaz B2B dedicada (facturación consolidada, tarifas negociadas) se
  **diseña** junto con la API B2B pero **no** se construye en el MVP.

## 5.5.4 Multi-moneda y multi-idioma (S5)

**Decisión: preparado en la estructura, una sola configuración activa en el MVP
(COP, es-CO).**

- **Idioma:** textos externalizados en archivos de recursos (`i18n/es-CO.json`);
  añadir un idioma = añadir un archivo + entrada en el selector. Ningún texto
  hardcodeado en componentes.
- **Moneda:** los precios llegan de la API con `{ monto, moneda }` (la columna
  `moneda` ya existe en `TARIFA`/`RESERVA` — 5.3). El frontend **formatea** según
  `Intl.NumberFormat` con el locale activo; **no convierte** importes (la
  conversión, si se necesita, es responsabilidad del backend con una tabla de tipos
  de cambio).
- **Implicación estructural:** el estado global de la SPA incluye `locale` y
  `currency`; los componentes de precio y fecha los consumen de contexto, no de
  constantes. Esto es lo único que el MVP "paga" por adelantado para no rehacer la
  UI al internacionalizar.

## 5.5.5 Componentes de la SPA (pasajero) y su mapeo a la API

| Pantalla / componente | Endpoint(s) del backend | FR |
|---|---|---|
| Buscador (origen, destino, fecha, nº pax, cabina) | `GET /flights/search` | FR-01, FR-02, FR-03 |
| Resultados (directos + con escala, precio por tarifa) | — (render del resultado) | FR-03 |
| Selección de itinerario + datos de pasajeros | `GET /flights/{id}/availability` (polling) | NFR-03 |
| Confirmación / hold | `POST /reservations` → código, o **409** | FR-04, FR-06, NFR-03 |
| Pago | (token del proveedor) + `POST /reservations/{code}/pay` | FR-08, NFR-06 |
| Consultar reserva (código + apellido) | `GET /reservations/{code}` | FR-12 |
| Cancelar | `POST /reservations/{code}/cancel` | FR-09 |

> El MVP implementa las pantallas de **búsqueda → selección → confirmación (hold) →
> código de reserva** y **consultar reserva**. Pago y cancelación quedan como
> pantallas de apoyo según el tiempo disponible.

## 5.5.6 Ajustes durante la implementación

El frontend se implementó en `frontend/` (React 18 + Vite 5 + react-router 6).
Corresponde con el diseño de arriba; las diferencias y decisiones concretas:

| # | Diseño (5.5.x) | Implementación | Motivo |
|---|---|---|---|
| F1 | SPA React + Vite servida como estático | Igual. `npm run build` → `dist/` estático; en desarrollo, proxy `/api` → `localhost:8000` | — |
| F2 | Pantallas búsqueda → selección → confirmación → código, y consultar reserva | Implementadas las 4 (`BuscarPage`, `SeleccionPage`, `ConfirmacionPage`, `MiReservaPage`) | alcance MVP de 5.5.5 |
| F3 | Pago y cancelación como pantallas de apoyo | **No** se construyeron (el backend tampoco expone `POST /pay` ni `/cancel` en el MVP — ver `docs/06` D6). La UI las omite en vez de mostrar botones muertos | coherencia con el alcance del backend |
| F4 | Manejo del 409 al confirmar (5.5.2) | `api.js` lanza `ApiError` con `status`; `SeleccionPage` captura 409 → mensaje + `navigate("/buscar")` | — |
| F5 | Polling ligero de disponibilidad cada ~15 s (5.5.2) | `SeleccionPage` hace `setInterval` de 15 s a `GET /flights/{id}/availability` por cada tramo; se limpia al desmontar | — |
| F6 | i18n: textos externalizados, sin literales en componentes (5.5.4) | `src/i18n/es-CO.json` + `makeT(locale)`; todos los textos visibles pasan por `t()` | — |
| F7 | Multi-moneda: formatear con `Intl`, no convertir (5.5.4) | `useFormatters().money(monto, moneda)` usa `Intl.NumberFormat` con el `moneda` que devuelve la API | — |
| F8 | Estado global `locale`/`currency` por contexto (5.5.4) | `ConfigProvider` / `useConfig`; en el MVP los valores son fijos (`es-CO`, `COP`), pero los componentes los leen de contexto | — |
| F9 | Vista por rol para agentes de agencia (5.5.3) | El flujo es el mismo; `SeleccionPage` permite elegir canal `AGENCIA` + `id_agencia`, y `MiReservaPage` muestra la comisión cuando `monto_comision > 0`. No hay login ni rol persistente (el backend del MVP no autentica) | el MVP no tiene autenticación; se expone la capacidad de canal sin la gestión de sesión |
| F10 | CORS | Se añadió `CORSMiddleware` al backend (`app/main.py`), configurable con `CORS_ORIGINS` en `.env` | la SPA es un origen distinto (Vite :5173 o el sitio S3) |

Ninguna diferencia obligó a cambiar el modelo ER ni la API; F3/F9 son
consecuencia del alcance ya acordado del backend, no cambios de diseño.
