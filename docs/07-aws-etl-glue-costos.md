# 5.7 Implementación AWS — ETL, Glue Data Catalog y costos

> Código: [`analytics/schema_olap.sql`](../analytics/schema_olap.sql), [`etl/etl.py`](../etl/etl.py), infraestructura en [`infra/cdk/`](../infra/cdk/)
> Diagrama de arquitectura AWS: [`diagrams/07-arquitectura-aws.drawio`](diagrams/07-arquitectura-aws.drawio)
> Referencias: FR/NFR en [01](01-requisitos-funcionales.md)/[02](02-requisitos-no-funcionales.md), modelo OLTP en [03](03-modelo-entidad-relacion.md), backend en [04](04-arquitectura-backend.md).

## 5.7.1 Qué se implementó

| Requisito del enunciado | Implementación |
|---|---|
| BD transaccional con el modelo de 5.3 | RDS PostgreSQL `aerolinea-oltp` (esquema de la migración `0001`) |
| 2ª BD PostgreSQL analítica (OLAP) que recibe copia de ≥1 tabla/vista vía ETL | RDS PostgreSQL `aerolinea-olap`, esquema **estrella** ([`schema_olap.sql`](../analytics/schema_olap.sql)) |
| Proceso ETL entre ambas | Script Python [`etl/etl.py`](../etl/etl.py) — `EXTRACT` (1 consulta que une el OLTP a nivel de segmento) → `TRANSFORM` (desnormaliza + deriva columnas) → `LOAD` (upsert idempotente) |
| Ambas BD registradas en AWS Glue Data Catalog | El stack CDK ([`infra/cdk/lib/aerolinea-stack.ts`](../infra/cdk/lib/aerolinea-stack.ts)) crea 1 database `aerolinea_catalog`, 2 conexiones JDBC y 2 crawlers (prefijos `oltp_` / `olap_`) |

**Evidencia local** (mismo código, PostgreSQL local): el ETL cargó 14 segmentos de
reserva y las 3 vistas de negocio responden — ver
[`docs/evidencia/etl-vistas-negocio.txt`](evidencia/etl-vistas-negocio.txt).

## 5.7.2 ¿Qué se copia al OLAP y cómo?

**Qué:** las **reservas a nivel de segmento** (`fact_reserva_segmento`, grano = un
tramo de una reserva) más sus dimensiones `dim_ruta`, `dim_vuelo`, `dim_tarifa`,
`dim_tiempo`, `dim_canal`.

**No se copia tal cual — se transforma:**
- **Desnormalización:** el hecho ya trae `id_ruta`, `id_tarifa`, `id_canal`, etc.;
  una consulta analítica no necesita recorrer 8 tablas como en el OLTP.
- **Columnas derivadas:** `par_ruta` (`BOG-MDE`), `ventana_compra`
  (`anticipada`/`última hora` según `dias_anticipacion_min`), `temporada`
  (`ALTA`/`BAJA` según el mes), banderas `es_confirmada`/`es_cancelada`/`es_expirada`.
- **Comisión prorrateada:** `reserva.monto_comision` (total) se reparte por
  segmento según su peso en el `monto_total`.
- **`dim_tiempo`** se genera en el ETL (no existe en el OLTP): un registro por
  fecha con año/mes/día de semana/temporada.

**Por qué el esquema OLAP ≠ OLTP** (relación con la normalización de 5.3): el OLTP
está en **3FN** porque su prioridad es la **integridad en escritura** (evitar
anomalías, `SELECT ... FOR UPDATE` sobre filas pequeñas — NFR-03/04). El OLAP tiene
la prioridad opuesta: **lecturas analíticas rápidas** con pocos joins → esquema
estrella desnormalizado. Son dos modelos para dos cargas de trabajo distintas; por
eso también viven en **instancias separadas** (el análisis no compite por los locks
del transaccional — NFR-08).

**Las 3 preguntas de negocio del enunciado** se responden con vistas sobre el hecho:

| Pregunta | Vista |
|---|---|
| Ocupación por ruta | `v_ocupacion_por_ruta` (pax confirmados / asientos ofertados, por ruta y mes) |
| Ingresos por tarifa | `v_ingresos_por_tarifa` (ingreso y comisión por clase de tarifa, cabina, ventana de compra) |
| Patrones de cancelación | `v_patrones_cancelacion` (% cancelación e ingreso perdido por ruta, tarifa, canal, temporada) |

## 5.7.3 ¿Con qué frecuencia corre el ETL?

**Decisión: diaria / on-demand (cron), no event-triggered.**

| Opción | Freshness | Costo / complejidad | ¿Se elige? |
|---|---|---|---|
| **Una sola vez** | datos congelados | mínimo | No — la gerencia quiere seguimiento continuo |
| **Periódica (diaria)** | ≤ 24 h | 1 ejecución/día, trivial | **Sí.** El análisis comercial (ocupación, ingresos, cancelaciones) se revisa por día/semana; no necesita datos al segundo. |
| **Event-triggered** (cada reserva dispara ETL) | segundos | alto: cola/lambda por evento, muchas ejecuciones, carga constante sobre el OLTP | No — sobredimensionado para el volumen de una aerolínea regional (S9) |

El script es idempotente (`upsert` por `id_segmento_itinerario`), así que una
ejecución fallida se puede reintentar sin duplicar. En AWS: un cron en la EC2
(`0 3 * * * python etl/etl.py`) o un EventBridge Schedule.

## 5.7.4 ¿Por qué el ETL es un script Python y no un Glue Job?

| | Script Python (elegido) | AWS Glue Job (PySpark) |
|---|---|---|
| Complejidad de configuración en el Learner Lab | baja: solo necesita las 2 URLs de conexión | alta: rol de Glue, conexión JDBC, driver, VPC, endpoints, script en S3 |
| Legibilidad / defensa oral | alta: 1 archivo, SQL explícito | media: DynamicFrames, transformaciones Spark |
| Escala (volumen de una aerolínea regional, S9) | suficiente (miles de filas/día) | pensado para TB; ocioso aquí |
| Costo | corre en la EC2 que ya existe → **$0 extra** | DPU-hora facturado por ejecución |
| Portabilidad | corre igual en local y en AWS | atado a Glue |

**Glue Job PySpark queda documentado como evolución:** si el volumen creciera a
millones de reservas/día, el `EXTRACT`/`TRANSFORM` se movería a un Glue Job que lee
el OLTP por JDBC en paralelo y escribe el OLAP; el `schema_olap.sql` no cambiaría.
**Glue sí se usa** — para el **Data Catalog**, que es requisito explícito.

## 5.7.5 Conexión de ambas BD al Glue Data Catalog

El stack CDK ([`infra/cdk/lib/aerolinea-stack.ts`](../infra/cdk/lib/aerolinea-stack.ts))
declara los recursos de Glue como parte de la infraestructura:

1. **Database del catálogo:** `aerolinea_catalog` (`CfnDatabase`).
2. **2 conexiones JDBC** (`conn-oltp`, `conn-olap`): URL
   `jdbc:postgresql://<endpoint-rds>:5432/aerolinea`, usuario/clave, y
   `PhysicalConnectionRequirements` (subred + security group de la VPC por defecto
   del Lab, con el puerto 5432 abierto).
3. **2 crawlers** (`crawler-oltp`, `crawler-olap`) con el ARN de `LabRole`,
   target `JdbcTargets` apuntando a `aerolinea/public/%`, y prefijos de tabla
   `oltp_` / `olap_` para distinguirlas en el catálogo.
4. Tras el despliegue se arrancan los crawlers (`aws glue start-crawler`) y en
   unos minutos las 19 tablas del OLTP y las 6 tablas + 3 vistas del OLAP quedan
   visibles como metadatos:
   `aws glue get-tables --database-name aerolinea_catalog`.

**Acceso de red:** las RDS son `publicly-accessible` en el MVP (Learner Lab) con un
security group que permite 5432 desde el propio SG (Glue) y desde la EC2. El
`LabRole` ya tiene los permisos de Glue y de lectura que necesitan los crawlers.

## 5.7.6 Justificación de los servicios AWS

Cada servicio se conecta a (1) un FR/NFR concreto de 5.1/5.2 y (2) uno o más
pilares del **AWS Well-Architected Framework** (Seguridad, Fiabilidad, Eficiencia
del rendimiento, Optimización de costos, Excelencia operativa, Sostenibilidad).

| AWS Service | Alternativa considerada | Requisito (FR/NFR) que soporta la elección | Pilar(es) Well-Architected |
|---|---|---|---|
| **RDS PostgreSQL — `aerolinea-oltp`** (`db.t3.micro`, single-AZ, cifrada) | Aurora Serverless v2; PostgreSQL autogestionado en EC2 | **NFR-03/04**: `SELECT ... FOR UPDATE` y transacciones ACID exigen un motor relacional real. **NFR-07**: cifrado en reposo (`StorageEncrypted`) gestionado. | **Fiabilidad** (backups automáticos, recuperación gestionada). **Seguridad** (cifrado KMS, sin gestionar parches del SO). **Optimización de costos** (t3.micro cabe en el presupuesto del Lab; Aurora es más caro para este volumen). |
| **RDS PostgreSQL — `aerolinea-olap`** (`db.t3.micro`) | Redshift; Athena sobre S3 (Parquet) | Requisito explícito 5.7 (*"segunda base PostgreSQL analítica"*). **FR-18**: servir reportes de ocupación/ingresos/cancelaciones. | **Eficiencia del rendimiento** (esquema estrella = consultas analíticas con pocos joins). **Optimización de costos** (Redshift mínimo cuesta ~10× más; innecesario para el volumen de S9). |
| **Script ETL en la EC2** (Python + cron) | AWS Glue Job (PySpark); AWS Data Pipeline; DMS | **FR-18** + relación OLTP→OLAP del pipeline (5.4.6). El volumen (S9) no justifica Spark. | **Optimización de costos** (reutiliza la EC2 de la API → $0 extra; Glue factura por DPU-hora). **Excelencia operativa** (un archivo legible, idempotente, versionado). **Sostenibilidad** (sin clúster ocioso). |
| **AWS Glue Data Catalog + 2 crawlers JDBC** | Registro manual de tablas; catálogo propio | Requisito explícito 5.7 (ambas BD *"visibles y consultables como metadatos desde Glue"*). | **Excelencia operativa** (metadatos centralizados y auto-descubiertos; base para futuros Athena/Glue Jobs). |
| **EC2 `t3.small`** (API FastAPI + cron ETL) | AWS Lambda + API Gateway; Fargate; Elastic Beanstalk | Todos los FR (host del monolito de 5.4). **NFR-01/02**: latencia predecible sin cold start. | **Optimización de costos** (una instancia pequeña sirve API + ETL; Lambda añadiría complejidad de empaquetado y VPC). **Excelencia operativa** (despliegue simple: `git pull` + `systemd`). |
| **IAM — `LabRole` / perfil de instancia** | Usuario IAM con access keys de larga duración | **NFR-07**: no incrustar credenciales; el Learner Lab rota la sesión. | **Seguridad** (credenciales temporales, principio de mínimo privilegio del Lab). |
| **VPC por defecto + Security Group** (5432 solo desde el SG y la EC2) | RDS público sin restricción; VPC dedicada con subredes privadas + NAT | **NFR-07**: aislar la BD del acceso público general. | **Seguridad** (superficie de red mínima). *Trade-off documentado:* subredes privadas + NAT serían lo ideal en producción; el Lab no lo permite cómodamente, se deja RDS accesible con SG restringido. |
| **Amazon S3** (respaldo de `schema_olap.sql`, exports de reportes) | EBS; almacenamiento local | Soporte a **FR-18** (compartir extractos de reportes). | **Optimización de costos** (centavos/mes). **Fiabilidad** (durabilidad 11 nueves). |

## 5.7.7 Proyección de costos mensual

> **Nota sobre la fuente.** AWS Academy Learner Lab **bloquea Cost Explorer**
> (`ce:GetCostAndUsage` tiene un *explicit deny* en la política del rol) y no
> expone facturación real —solo un contador de crédito restante—. Por eso la
> proyección se hace, como pide el enunciado, con la **AWS Pricing Calculator /
> precios públicos on-demand** de `us-east-1`. Los recursos y su dimensionamiento
> son exactamente los que declara el stack CDK
> ([`infra/cdk/lib/aerolinea-stack.ts`](../infra/cdk/lib/aerolinea-stack.ts)).

**Supuestos explícitos:**
- Región **`us-east-1`**, precios públicos on-demand (sept. 2026), USD, sin capa
  gratuita (la cuenta del Lab no la tiene).
- Se dan **dos columnas**: **730 h/mes (24/7)**, que es lo que calcula la AWS
  Pricing Calculator por defecto; y **uso real del Lab** (~6 h/día × 20 días =
  **120 h/mes**, apagando con `deploy.sh destroy` al terminar cada sesión).
- Volumen actual (S9): ~20 rutas, ~600 instancias de vuelo/mes, ~5 000 reservas/mes
  → datos del orden de **decenas de MB**.
- ETL: **1 ejecución/día**, ~30 s, sobre la EC2 ya contabilizada.

### Desglose por servicio (formato AWS Pricing Calculator)

| Servicio | Configuración | Precio unitario | Cómputo 24/7 | Uso real Lab (120 h) |
|---|---|---|---|---|
| **Amazon RDS** — `aerolinea-oltp` | PostgreSQL 16, `db.t3.micro` (2 vCPU burst, 1 GiB), Single-AZ | $0.018 / h | $13.14 | $2.16 |
| **Amazon RDS** — `aerolinea-olap` | PostgreSQL 16, `db.t3.micro`, Single-AZ | $0.018 / h | $13.14 | $2.16 |
| **RDS — almacenamiento** | gp3, 20 GB × 2 instancias = 40 GB | $0.115 / GB-mes | $4.60 | $4.60 |
| **RDS — backups** | Retención 1 día; volumen ≤ tamaño de la BD → dentro del backup gratuito | — | $0.00 | $0.00 |
| **Amazon EC2** — `aerolinea-api` | `t3.small` (2 vCPU burst, 2 GiB), Linux on-demand | $0.0208 / h | $15.18 | $2.50 |
| **EC2 — almacenamiento** | EBS gp3, 20 GB, cifrado | $0.08 / GB-mes | $1.60 | $1.60 |
| **AWS Glue — Data Catalog** | ~28 tablas (19 `oltp_*` + 9 `olap_*`). Primer 1 M de objetos y de solicitudes: gratis | $0.00 | $0.00 | $0.00 |
| **AWS Glue — Crawlers** | 2 crawlers × ~2 min/ejecución. Mín. facturable 10 min = 1/6 DPU-h. 24/7: 2/día; Lab: 1/sesión | $0.44 / DPU-h | $4.40 (≈60 ejec.) | $0.15 (≈20 ejec.) |
| **Amazon S3** | Tarball de código (~0.2 MB) + `schema_olap.sql`; pocos GET/PUT | $0.023 / GB-mes | $0.02 | $0.02 |
| **Transferencia de datos** | EC2 ↔ RDS ↔ Glue dentro de la misma VPC/AZ; salida < 1 GB/mes (gratis) | — | $0.00 | $0.00 |
| | | **TOTAL** | **≈ $52.2 / mes** | **≈ $15.9 / mes** |

El uso real en el Lab (~$16/mes) cabe holgadamente en el crédito asignado
(~$50–100). El total 24/7 (~$52/mes) es la cifra que devuelve la AWS Pricing
Calculator para este conjunto de recursos.

### Escenario ×10 (volumen o frecuencia multiplicados por 10)

Interpretación: **10× reservas** (~50 000/mes, datos de cientos de MB a ~2 GB) y/o
**ETL cada 2–3 h** en vez de diario. Cifras sobre la columna **24/7**.

| Servicio | Cambio con ×10 | Costo base 24/7 | Costo ×10 24/7 | Comentario / pilar |
|---|---|---|---|---|
| RDS OLTP | `db.t3.micro` → **`db.t3.small`** (2 GiB) para absorber más escrituras y el lock bajo carga | $13.14 | ~$26.30 | El cuello de botella sigue siendo la contención del lock (NFR-04), no el tamaño; se sube **una talla**, no ×10. **Optimización de costos:** escalar vertical 1 paso antes que sharding. |
| RDS OLAP | `db.t3.micro` → **`db.t3.small`** | $13.14 | ~$26.30 | El hecho crece linealmente; las vistas agregan. **Eficiencia del rendimiento.** |
| RDS almacenamiento | 40 GB → ~120 GB | $4.60 | ~$13.80 | Lineal con el volumen. |
| EC2 (API + ETL) | ETL ×8 más frecuente, pero cada corrida sigue siendo segundos; la API aguanta | $15.18 + $1.60 | ~$16.78 (sin cambio) | El script Python escala bien aquí. **Sostenibilidad:** sin infra nueva. |
| Glue Crawlers | ejecutar tras cada carga (×8/día) → ~40 DPU-h/mes | $4.40 | ~$17.60 | Se reduce corriendo el crawler **solo cuando cambia el esquema**, no en cada carga → volvería a ~$4. **Optimización de costos.** |
| Glue Data Catalog + S3 | ~280 objetos, aún gratis; S3 ~2 GB | $0.02 | ~$0.05 | Dentro del nivel gratuito del catálogo. |
| **TOTAL ×10 (24/7)** | | **≈ $52 / mes** | **≈ $117 / mes** | **~2.25×** el costo base, **no ×10** |

**Conexión con los pilares Optimización de costos y Sostenibilidad:** al
multiplicar el volumen por 10, el costo sube solo ~2,25× porque (a) los servicios
de datos escalan **verticalmente un paso**, no proporcionalmente; (b) el ETL y el
catálogo **no escalan con el volumen** en este rango (script sobre la EC2
existente, catálogo gratuito); (c) el crawler se puede desacoplar de la carga
para no pagar cómputo redundante. Si el volumen siguiera creciendo (×100), la
migración recomendada sería OLAP → **Athena sobre S3/Parquet** (se paga por
consulta y por almacenamiento comprimido, cero cómputo ocioso) y ETL → **Glue
Job**.

### Estimado en la AWS Pricing Calculator

El estimado con estos mismos recursos y precios está guardado en
`https://calculator.aws/#/estimate` — [ pegar aquí el enlace público del
estimado y una captura de la pantalla de resumen ].

## 5.7.8 Diagrama de arquitectura AWS

[`diagrams/07-arquitectura-aws.drawio`](diagrams/07-arquitectura-aws.drawio) — muestra:
navegador → EC2 (FastAPI + cron ETL) → RDS OLTP; EC2/ETL → RDS OLAP; crawlers JDBC
desde Glue a ambas RDS → Glue Data Catalog; todo en la VPC por defecto con el
security group restringido; `LabRole` como identidad.
