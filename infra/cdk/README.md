# Infra CDK — Parcial 1 (AWS Academy Learner Lab)

Un solo stack (`AerolineaParcial1`) que crea **toda** la infraestructura del
parcial y deja la API funcionando sola:

| Recurso | Para qué |
|---|---|
| **VPC** por defecto del Lab (`fromLookup`) | red (el Lab no deja crear NAT/EIP) |
| **Security group** `aerolinea-sg` | 22 + 8000 desde tu IP; 5432 solo interno + tu IP |
| **RDS `aerolinea-oltp`** `db.t3.micro` PG16, cifrada | base transaccional (modelo 5.3) — NFR-07 |
| **RDS `aerolinea-olap`** igual | esquema estrella OLAP |
| **EC2 `aerolinea-api`** `t3.small` AL2023 | corre la API; el `UserData` baja el tarball de código de S3, migra, carga datos, corre el ETL y levanta `uvicorn` como servicio systemd |
| **Glue**: 1 database + 2 conexiones JDBC + 2 crawlers | Data Catalog (5.7), prefijos `oltp_` / `olap_` |
| Tarball de código en un bucket S3 del Lab | lo sube `deploy.sh`, lo descarga la EC2 al arrancar (no es un asset de CDK) |

**Restricciones del Learner Lab que respeta:**
- **No hay `cdk bootstrap`** (el toolkit del CDK necesita crear roles IAM y el
  Lab lo prohíbe con `403 iam:CreateRole`). Por eso el despliegue es:
  `cdk synth` (genera la plantilla) + `aws cloudformation deploy` (la aplica con
  las credenciales del Lab). El stack usa `DefaultStackSynthesizer({
  generateBootstrapVersionRule: false })` para no depender del toolkit.
- **No usa assets de CDK** (que requieren el bucket del bootstrap). `deploy.sh`
  empaqueta el repo en un tarball, lo sube a un bucket S3 existente del Lab
  (uno que empiece por `big-data`, o crea `aerolinea-code-<cuenta>`), y el
  `UserData` de la EC2 lo baja.
- **No crea roles IAM**: la EC2 usa el instance profile preexistente
  `LabInstanceProfile` (se borran los nodos Role/InstanceProfile que CDK añade
  por defecto); los crawlers usan el ARN de `LabRole`.
- RDS `publiclyAccessible: true` para que el crawler de Glue y tu `psql` las
  alcancen; el acceso real lo cierra el security group.

## Requisitos

- Node 18+ y `npm` (hay `node` v20 en este equipo).
- Credenciales del Lab activas. Copia el bloque **AWS Details → AWS CLI** del
  portal de AWS Academy en `~/.aws/credentials` bajo `[academy]` (o exporta
  `AWS_PROFILE`). Caducan al cerrar la sesión del Lab.

```bash
cd infra/cdk
npm install
aws sts get-caller-identity --profile academy   # debe responder con la cuenta del Lab
```

## Desplegar

```bash
AWS_PROFILE=academy ./deploy.sh
```

El script: resuelve cuenta/región, compila, elige/crea el bucket de código,
empaqueta y sube el repo, crea el par de claves `aerolinea-key.pem` si no
existe, hace `cdk synth`, aplica la plantilla con `aws cloudformation deploy`
restringiendo el acceso a **tu IP**, y arranca los crawlers de Glue.

Salidas del stack (`ApiUrl`, `OltpEndpoint`, `OlapEndpoint`, `SshCommand`, …)
se imprimen al final y quedan en CloudFormation.

### Verificar (evidencias del parcial)

```bash
API=$(aws cloudformation describe-stacks --stack-name AerolineaParcial1 \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

curl $API/health
curl "$API/flights/search?origen=BOG&destino=MDE&fecha=2026-09-10&pasajeros=1"

# prueba de concurrencia contra la API real
ssh -i aerolinea-key.pem ec2-user@${API#http://} -p 22   # o quita el :8000
#   dentro: cd /opt/aerolinea/backend
#   .venv/bin/python tests/concurrencia_http.py --preparar
#   .venv/bin/python tests/concurrencia_http.py --instancia 1 --tarifa 1 --n 20

# la evidencia del test de servicio la deja el UserData en:
#   /opt/aerolinea/docs/evidencia/prueba-concurrencia-aws.txt
#   (y el log completo del provisioning en /var/log/aerolinea-provision.log)

# Glue Data Catalog
aws glue get-tables --database-name aerolinea_catalog \
  --query 'TableList[].Name' --output table
```

Captura de pantalla para 5.7: consola → **AWS Glue → Data Catalog → Databases
→ aerolinea_catalog → Tables** (tablas `oltp_*` y `olap_*`).

## Destruir — SIEMPRE al terminar la sesión

```bash
AWS_PROFILE=academy ./deploy.sh destroy
```

Y en el portal: **End Lab**.

## Problemas frecuentes

| Síntoma | Arreglo |
|---|---|
| `no credentials` / `InvalidClientTokenId` | recopia el bloque *AWS CLI* del portal; caduca al cerrar la sesión |
| `403 iAM:CreateRole` en el deploy | normal: el Lab prohíbe crear roles. deploy.sh ya no hace `cdk bootstrap`; usa `aws cloudformation deploy`. Si ves un stack `CDKToolkit` en `CREATE_FAILED`, bórralo: `aws cloudformation delete-stack --stack-name CDKToolkit` |
| crawler queda `FAILED` | RDS y conexión Glue deben compartir SG y subred (el stack ya lo hace); espera a que la RDS esté `available` |
| `curl /health` no responde a los 2 min | el `UserData` tarda ~5 min (instala Python, migra, corre ETL). Mira `/var/log/aerolinea-provision.log` y `journalctl -u aerolinea` |
| `AccessDenied` al subir el tarball a S3 | el bucket elegido no es tuyo. Exporta `CODE_BUCKET=<bucket con permiso de escritura>` antes de `./deploy.sh` |
| credenciales caducadas a mitad del deploy | la sesión del Lab expiró (~4 h). Recopia el bloque *AWS CLI*, y relanza `./deploy.sh` (es idempotente) |
