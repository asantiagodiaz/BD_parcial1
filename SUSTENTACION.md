# Guía de sustentación

Cómo poner el sistema en marcha, todas las URLs, y qué mostrar en la defensa.

---

## 1. Componentes y dónde vive cada cosa

| Componente | Qué es | Dónde |
|---|---|---|
| **API** | FastAPI: buscar vuelos, crear reserva (con bloqueo pesimista), consultar reserva | EC2 `t3.small` en AWS Academy, o `uvicorn` local |
| **BD transaccional (OLTP)** | PostgreSQL, modelo E-R de 5.3, en 3FN | RDS `aerolinea-oltp`, o PostgreSQL local |
| **BD analítica (OLAP)** | PostgreSQL, esquema estrella, alimentada por el ETL | RDS `aerolinea-olap`, o PostgreSQL local |
| **ETL** | Script Python OLTP → OLAP (`etl/etl.py`) | corre en la EC2 (o local) |
| **Glue Data Catalog** | Cataloga ambas BD (`aerolinea_catalog`, tablas `oltp_*` / `olap_*`) | AWS Glue |
| **Frontend** | SPA React (búsqueda → selección → confirmación → consultar) | `npm run dev` local, apunta a la API |

---

## 2. URLs (cámbialas por las de tu sesión del Lab)

> La IP pública de la EC2 **cambia cada vez que el Lab reinicia la instancia**.
> Sácala así:
>
> ```bash
> cd infra/cdk
> AWS_PROFILE=academy aws ec2 describe-instances \
>   --filters "Name=tag:Name,Values=aerolinea-api" "Name=instance-state-name,Values=running" \
>   --query 'Reservations[].Instances[].PublicIpAddress' --output text
> ```
>
> O corre `AWS_PROFILE=academy ./validar.sh` — imprime la URL viva al final.

Llamando `<IP>` a esa dirección:

| Recurso | URL |
|---|---|
| API — health | `http://<IP>:8000/health` |
| API — documentación interactiva (Swagger) | `http://<IP>:8000/docs` |
| API — buscar vuelos | `http://<IP>:8000/flights/search?origin=BOG&dest=MDE&date=2026-09-10&pax=1` |
| API — consultar reserva | `http://<IP>:8000/reservations/<CODIGO>` |
| Frontend (local) | `http://localhost:5173` |
| Consola Glue — Data Catalog | AWS Console → Glue → Data Catalog → Databases → `aerolinea_catalog` → Tables |

**Endpoints RDS** (para DBeaver / psql):

| BD | Host | Puerto | Base | Usuario | Contraseña |
|---|---|---|---|---|---|
| OLTP | `aerolinea-oltp.<...>.rds.amazonaws.com` | 5432 | `aerolinea` | `aerolinea` | `aerolinea123` |
| OLAP | `aerolinea-olap.<...>.rds.amazonaws.com` | 5432 | `aerolinea` | `aerolinea` | `aerolinea123` |

Los hosts exactos salen de:
```bash
AWS_PROFILE=academy aws cloudformation describe-stacks --stack-name AerolineaParcial1 \
  --query "Stacks[0].Outputs" --output table
```

---

## 3. Poner todo en marcha

### 3.1 En AWS (Learner Lab)

1. **Inicia el Lab** (Start Lab → punto verde).
2. **Credenciales**: portal → *AWS Details → AWS CLI* → copia el bloque en
   `~/.aws/credentials` bajo `[academy]`. Caducan al cerrar la sesión.
3. **Despliega**:
   ```bash
   cd infra/cdk
   npm install
   AWS_PROFILE=academy ./deploy.sh
   ```
   Crea VPC/SG, 2× RDS cifradas, EC2 (que se auto-provisiona: migra la BD, carga
   datos, corre el ETL, levanta la API) y el Glue Data Catalog. Arranca los
   crawlers al final. ~10–12 min en total.
4. **Verifica**:
   ```bash
   AWS_PROFILE=academy ./validar.sh
   ```
   Debe dar **15 OK / 0 FALLA**.
5. **Al terminar** (siempre, para no gastar créditos):
   ```bash
   AWS_PROFILE=academy ./deploy.sh destroy
   ```
   Y *End Lab* en el portal.

Si `validar.sh` falla en la API por *timeout* y tu IP cambió:
`AWS_PROFILE=academy ./fix-mi-ip.sh`

### 3.2 En local (sin AWS)

```bash
# --- backend + bases de datos ---
cd backend
bash setup-postgres-local.sh          # instala PostgreSQL y crea las 2 bases
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head        # crea el esquema OLTP (modelo 5.3)
.venv/bin/python -m seed.load         # datos de ejemplo
.venv/bin/python -m seed.demo_reservas # 14 reservas con estados variados
.venv/bin/uvicorn app.main:app --reload   # API en http://localhost:8000

# --- ETL (otra terminal) ---
cd .. && backend/.venv/bin/python etl/etl.py --init && backend/.venv/bin/python etl/etl.py --full

# --- frontend (otra terminal) ---
cd frontend
npm install
cp .env.example .env                  # vacío = usa el proxy a localhost:8000
npm run dev                           # http://localhost:5173
```

### 3.3 Solo el frontend contra la API en AWS

```bash
cd frontend && npm install
IP=$(AWS_PROFILE=academy aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=aerolinea-api" "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text)
echo "VITE_API_URL=http://$IP:8000" > .env
npm run dev
```

---

## 4. Guion de demostración

### 4.1 Con el frontend (http://localhost:5173)

1. **Buscar** BOG → MDE, fecha dentro de los próximos 30 días, 1 pasajero.
   Muestra opciones directas y con escala, con precio por tarifa.
2. **Seleccionar** una opción → llenar datos del pasajero → **Confirmar**.
   Sale el **código de reserva** y el estado `RETENIDA` (hold de 15 min).
3. **Mi reserva** → pegar el código → se ve la reserva completa con su
   **historial de eventos** (append-only, NFR-09).

### 4.2 La prueba de concurrencia (lo más importante — NFR-03)

**Forma recomendada — en local** (no necesita AWS ni la API levantada; usa la
capa de servicio directamente con 20 hilos):

```bash
cd backend
.venv/bin/pytest tests/test_concurrencia.py -s
```

Resultado:
```
reservas OK (hold)     : 1
rechazos HTTP 409      : 19
invariante (v+r <= t)  : 60 <= 60  -> OK
2 passed
```

**Contra la API desplegada en AWS** (opcional; la IP cambia cada vez que el Lab
reinicia la EC2, así que hay que resolverla en el momento). Primero, en tu
máquina:

```bash
cd infra/cdk
IP=$(AWS_PROFILE=academy aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=aerolinea-api" "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text)
ssh -i aerolinea-key.pem ec2-user@$IP
```

Y **ya dentro de la EC2** (el prompt cambia a `[ec2-user@ip-...]`):

```bash
cd /opt/aerolinea/backend
P=$(.venv/bin/python tests/concurrencia_http.py --preparar); echo "$P"
I=$(echo "$P" | grep -oP 'instancia=\K[0-9]+'); T=$(echo "$P" | grep -oP 'tarifa=\K[0-9]+')
.venv/bin/python tests/concurrencia_http.py --instancia $I --tarifa $T --n 20
```

Resultado esperado: **1 × 201 Created, 19 × 409 Conflict, sin sobreventa**.

Evidencias ya capturadas: [`docs/evidencia/prueba-concurrencia.txt`](docs/evidencia/prueba-concurrencia.txt)
(local) y [`docs/evidencia/prueba-concurrencia-aws.txt`](docs/evidencia/prueba-concurrencia-aws.txt) (AWS).

### 4.3 El pipeline analítico (5.7)

En la consola de **AWS Glue → Data Catalog → aerolinea_catalog → Tables**:
se ven las **19 tablas `oltp_*`** y las **9 `olap_*`** (hecho + 5 dimensiones +
3 vistas).

Las 3 preguntas de negocio, contra la RDS OLAP (DBeaver o psql):
```sql
SELECT * FROM v_ocupacion_por_ruta;      -- ocupación por ruta
SELECT * FROM v_ingresos_por_tarifa;     -- ingresos por tarifa
SELECT * FROM v_patrones_cancelacion;    -- patrones de cancelación
```

---

## 5. Datos de ejemplo (para armar consultas en la demo)

- **Aeropuertos:** BOG, MDE, CTG, CLO, BAQ
- **Rutas con vuelos:** BOG↔MDE, BOG↔CTG, BOG↔CLO, MDE↔CTG, CLO↔BAQ
- **Fechas:** hay instancias de vuelo para los ~30 días siguientes a la carga
- **Cabinas:** `ECONOMICA`, `EJECUTIVA`
- **Reservas demo** (`seed.demo_reservas`): 14 reservas → 9 confirmadas, 3
  canceladas, 2 retenidas

Ver los pasajeros y sus reservas:
```sql
SELECT p.nombre_completo, r.codigo_reserva, r.estado,
       i.iata_origen || ' → ' || i.iata_destino AS ruta, r.monto_total
FROM pasajero p
JOIN reserva_pasajero rp ON rp.id_pasajero = p.id_pasajero
JOIN reserva r           ON r.id_reserva   = rp.id_reserva
JOIN itinerario i        ON i.id_reserva   = r.id_reserva
ORDER BY r.creada_en DESC;
```

---

## 6. Preguntas frecuentes en la defensa

**¿Por qué bloqueo pesimista y no optimista?**
El asiento en un vuelo popular tiene alta contención y el costo de un reintento
fallido para el usuario es alto (pierde la tarifa). El optimista genera muchos
reintentos bajo contención; el pesimista serializa solo las filas de inventario
afectadas, por milisegundos, con transacción corta y sin llamadas externas
dentro del `BEGIN/COMMIT`. Detalle en `docs/04` §5.4.

**¿Cómo evitan deadlocks?**
Los `SELECT ... FOR UPDATE` se hacen siempre en orden ascendente de
`id_instancia_vuelo`. Dos reservas que tocan los mismos vuelos los bloquean en
el mismo orden → nunca hay ciclo de espera.

**¿Por qué monolito?**
Una sola transacción ACID resuelve el problema central (no sobrevender).
Repartir el inventario entre servicios obligaría a saga/2PC — más frágil para
lo que pide el parcial. Un despliegue, una BD transaccional.

**¿Por qué inventario por cabina y no por silla?**
La silla se asigna en el check-in (S7). Durante la reserva solo importa el
contador disponible por cabina. Modelar 180 sillas por vuelo no aporta y
complica el bloqueo.

**¿Por qué dos RDS y no dos esquemas en una?**
Aislar la carga analítica (consultas largas de reportes) de la OLTP
(transacciones cortas). NFR-08. El OLAP además es esquema estrella, distinto
del OLTP en 3FN.

**¿Por qué el ETL es un script y no un Glue Job?**
Volumen bajo (miles de segmentos), frecuencia diaria, corre en la EC2 que ya
existe → $0 extra y es trazable. Glue se usa solo para el Data Catalog, que es
requisito explícito. `docs/07` §5.7.4.

**¿Qué pasa si el tráfico se multiplica por 10?**
Los costos suben ~2,5×, no 10× (de ~$48 a ~$118/mes 24/7): EC2 y RDS suben de
tamaño, S3 y Glue casi no cambian. Conecta con los pilares Optimización de
costos y Sostenibilidad. `docs/07`.

**¿Dónde está la seguridad de datos de pago?**
Nunca se almacena PAN/CVV (NFR-06): el pago se delega a una pasarela externa y
solo se guarda un token. PII cifrada en reposo (RDS `StorageEncrypted`) y TLS
en tránsito (NFR-07). Sin credenciales de larga vida: se usa `LabRole`.

**¿El código refleja el diseño de 5.4?**
Sí, con 6 desviaciones menores declaradas en `docs/06` §5.6.3 (D1–D6). Ninguna
obligó a cambiar el modelo E-R. Ejemplo (D1): el `FOR UPDATE` bloquea todas las
filas de inventario del vuelo, no solo la cabina pedida — más simple y
igualmente correcto.

---

## 7. Trazabilidad

Los 18 FR y los 9 NFR están definidos en `docs/01` / `docs/02` y citados en los
documentos de arquitectura e implementación (`03`–`07`). Cada decisión de
arquitectura menciona el FR/NFR que la origina.
