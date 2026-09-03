#!/usr/bin/env bash
# =====================================================================
# Valida que todo el despliegue del Parcial 1 este funcionando en el Lab.
# No modifica nada; solo lee y reporta OK / FALLA por cada chequeo.
#
#   AWS_PROFILE=academy ./validar.sh
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE="${AWS_PROFILE:-academy}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
STACK="AerolineaParcial1"

ok=0; fail=0
chk()  { printf "  [ OK ] %s\n" "$1"; ok=$((ok+1)); }
bad()  { printf "  [FALLA] %s\n" "$1"; fail=$((fail+1)); }
hdr()  { printf "\n== %s ==\n" "$1"; }

# ---------- credenciales ----------
hdr "Credenciales del Lab"
if ACC=$(aws sts get-caller-identity --query Account --output text 2>/dev/null); then
  chk "sesion activa (cuenta $ACC)"
else
  bad "no hay credenciales validas -> recopia el bloque 'AWS CLI' del portal"
  echo; echo "Sin credenciales no puedo validar el resto. Aborto."; exit 1
fi

# ---------- stack ----------
hdr "CloudFormation"
ST=$(aws cloudformation describe-stacks --stack-name "$STACK" \
      --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)
case "$ST" in
  CREATE_COMPLETE|UPDATE_COMPLETE) chk "stack $STACK en $ST" ;;
  NONE) bad "el stack $STACK no existe -> corre ./deploy.sh"; ;;
  *)    bad "stack en estado $ST (revisa 'aws cloudformation describe-stack-events --stack-name $STACK')" ;;
esac

get_out() { aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text 2>/dev/null; }
OLTP_HOST=$(get_out OltpEndpoint)
OLAP_HOST=$(get_out OlapEndpoint)

# La IP publica de la EC2 cambia cada vez que el Lab detiene/reanuda la instancia,
# asi que el output 'ApiUrl' del stack queda obsoleto. La resolvemos en vivo.
EC2_IP=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=aerolinea-api" \
  "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text 2>/dev/null)
API_URL=""
[ -n "$EC2_IP" ] && API_URL="http://$EC2_IP:8000"

# ---------- EC2 ----------
hdr "EC2 (servidor de la API)"
EC2_STATE=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=aerolinea-api" \
  "Name=instance-state-name,Values=running,pending,stopping,stopped" \
  --query 'Reservations[].Instances[].State.Name' --output text 2>/dev/null)
[ "$EC2_STATE" = "running" ] && chk "instancia aerolinea-api running" \
  || bad "instancia aerolinea-api en estado '${EC2_STATE:-inexistente}'"

# ---------- RDS ----------
hdr "RDS (2 instancias PostgreSQL)"
for db in aerolinea-oltp aerolinea-olap; do
  read -r S ENC <<<"$(aws rds describe-db-instances --db-instance-identifier "$db" \
    --query 'DBInstances[0].[DBInstanceStatus,StorageEncrypted]' --output text 2>/dev/null)"
  [ "$S" = "available" ] && chk "$db available" || bad "$db en estado '${S:-inexistente}'"
  [ "$ENC" = "True" ] && chk "$db cifrada en reposo (NFR-07)" || bad "$db NO cifrada"
done

# ---------- API ----------
hdr "API FastAPI"
if [ -n "$API_URL" ]; then
  H=$(curl -s --max-time 8 "$API_URL/health" 2>/dev/null)
  echo "$H" | grep -q '"status":"ok"' && chk "$API_URL/health responde {\"status\":\"ok\"}" \
    || bad "/health no responde OK (got: ${H:-timeout}) -> puede que el UserData aun este provisionando"

  S=$(curl -s --max-time 12 "$API_URL/flights/search?origin=BOG&dest=MDE&date=2026-09-10&pax=1" 2>/dev/null)
  echo "$S" | grep -q '"opciones"' && chk "/flights/search devuelve vuelos" \
    || bad "/flights/search no devuelve opciones (got: ${S:0:120})"
else
  bad "no hay ApiUrl en los outputs del stack"
fi

# ---------- Glue ----------
hdr "Glue Data Catalog"
for c in crawler-oltp crawler-olap; do
  read -r STATE LAST <<<"$(aws glue get-crawler --name "$c" \
    --query 'Crawler.[State,LastCrawl.Status]' --output text 2>/dev/null)"
  if [ "$LAST" = "SUCCEEDED" ]; then chk "$c: ultimo crawl SUCCEEDED (estado $STATE)"
  elif [ "$STATE" = "RUNNING" ]; then bad "$c aun RUNNING -> espera 2-3 min y reintenta"
  else bad "$c: LastCrawl='${LAST:-nunca}' estado='${STATE:-inexistente}'"
  fi
done
N_OLTP=$(aws glue get-tables --database-name aerolinea_catalog \
  --query "length(TableList[?starts_with(Name,'oltp_')])" --output text 2>/dev/null || echo 0)
N_OLAP=$(aws glue get-tables --database-name aerolinea_catalog \
  --query "length(TableList[?starts_with(Name,'olap_')])" --output text 2>/dev/null || echo 0)
[ "${N_OLTP:-0}" -ge 15 ] && chk "$N_OLTP tablas oltp_ catalogadas" || bad "solo $N_OLTP tablas oltp_ (esperado ~19)"
[ "${N_OLAP:-0}" -ge 6 ]  && chk "$N_OLAP tablas olap_ catalogadas" || bad "solo $N_OLAP tablas olap_ (esperado 9)"

# ---------- datos en las RDS (via la EC2) ----------
hdr "Datos en las RDS (consulta via SSH a la EC2)"
if [ -f aerolinea-key.pem ] && [ -n "$EC2_IP" ]; then
  OUT=$(timeout 30 ssh -i aerolinea-key.pem -o StrictHostKeyChecking=no \
        -o ConnectTimeout=10 ec2-user@"$EC2_IP" '
    cd /opt/aerolinea/backend && set -a && . .env && set +a
    .venv/bin/python - <<PY
import os, psycopg
o=psycopg.connect(os.environ["OLTP_DATABASE_URL"].replace("+psycopg",""))
a=psycopg.connect(os.environ["OLAP_DATABASE_URL"].replace("+psycopg",""))
def one(c,q):
    cur=c.cursor(); cur.execute(q); return cur.fetchone()[0]
print("instancias_vuelo", one(o,"select count(*) from instancia_vuelo"))
print("reservas", one(o,"select count(*) from reserva"))
print("fact_olap", one(a,"select count(*) from fact_reserva_segmento"))
PY' 2>/dev/null)
  echo "$OUT" | grep -q "instancias_vuelo" && {
    IV=$(echo "$OUT"|awk '/instancias_vuelo/{print $2}')
    RV=$(echo "$OUT"|awk '/reservas/{print $2}')
    FC=$(echo "$OUT"|awk '/fact_olap/{print $2}')
    [ "${IV:-0}" -gt 0 ] && chk "OLTP: $IV instancias de vuelo, $RV reservas" || bad "OLTP sin datos"
    [ "${FC:-0}" -gt 0 ] && chk "OLAP: $FC filas en fact_reserva_segmento" || bad "OLAP sin datos (falta correr el ETL)"
  } || bad "no pude consultar las RDS por SSH (revisa el par de claves / SG)"
else
  echo "  (omitido: falta aerolinea-key.pem o ApiUrl)"
fi

# ---------- resumen ----------
hdr "Resumen"
echo "  OK: $ok    FALLA: $fail"
echo
echo "  API en vivo:  ${API_URL:-<EC2 no running>}"
echo "  (la IP cambia cada vez que el Lab reinicia la EC2; usa siempre esta)"
if [ "$fail" -eq 0 ]; then
  echo "  -> Todo el despliegue esta funcionando."
  echo "     Ahora captura pantallas de: Glue (Tables), RDS (Encryption), EC2 (running)."
  exit 0
else
  echo "  -> Revisa los [FALLA] de arriba."
  exit 1
fi
