# Diagramas (draw.io)

Archivos `.drawio` editables. Abrir con [app.diagrams.net](https://app.diagrams.net)
o la extensión **Draw.io Integration** de VS Code.

| Archivo | Contenido | Sección |
|---|---|---|
| `03-modelo-entidad-relacion.drawio` | Modelo ER completo, notación Crow's Foot | 5.3 |
| `04-arquitectura-backend.drawio` | 2 pestañas: componentes del monolito + flujo de `POST /reservations` con bloqueo pesimista | 5.4 |
| `05-arquitectura-frontend.drawio` | Componentes de la SPA, mapeo a endpoints, decisión SPA vs SSR y manejo de 409 | 5.5 |
| `07-arquitectura-aws.drawio` | Arquitectura AWS: EC2 (API + cron ETL) + 2 RDS + Glue Data Catalog + S3 | 5.7 |

## Exportar a imagen para los Word

En draw.io: **File → Export as → PNG** (borde 10, escala 2x), guardar como
`<nombre>.png` en esta carpeta. El documento Word correspondiente referencia esa PNG.

El ER está organizado en **5 bandas verticales** (izq→der): catálogo/maestros,
programación de vuelos, inventario, núcleo de la reserva, pasajeros/billetes.

Colores usados en el ER:
- Azul: catálogo / maestros (aeropuertos, rutas, aeronaves, tarifas, agencias, cuentas).
- Verde: programación de vuelos (`VUELO_PROGRAMADO` vs. `INSTANCIA_VUELO`).
- Naranja: `INVENTARIO_ASIENTOS` — punto de control de sobreventa.
- Rojo: núcleo transaccional de la reserva.
- Morado: pasajeros, billetes, asignación de asiento.
- Amarillo: auditoría (`EVENTO_RESERVA`).

## Parcial 3

Copias de los `.drawio` de `parcial3/docs/diagrams/`. Allí están las imágenes (.png, .svg) y los scripts que los generan
(`generar_diagrama.py` y `generar_estrella.py`); si se cambian, regenerar allí y volver a copiar.

| Archivo | Contenido | Sección |
|---|---|---|
| `07-arquitectura-aws-parcial3.drawio` | Arquitectura AWS del P3: EC2 (API + PostgreSQL + consumidor en vivo) → Kinesis → Firehose → S3 → Athena CTAS → Glue | 5 |
| `08-modelo-estrella-parcial3.drawio` | Modelo estrella: `dim_date`, `dim_route` (SCD2), `dim_fare_class`, `fact_search`, `fact_booking_event` | 5 |
