#!/usr/bin/env bash
# =====================================================================
# Recorre la API desplegada: health -> buscar -> crear -> consultar.
# Resuelve solo la IP publica actual de la EC2.
#
#   AWS_PROFILE=academy ./demo.sh
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE="${AWS_PROFILE:-academy}"

IP=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=aerolinea-api" \
  "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text)
[ -n "$IP" ] || { echo "EC2 no esta running. Inicia el Lab."; exit 1; }
API="http://$IP:8000"
echo ">> API: $API"
echo ">> Swagger interactivo: $API/docs"
echo

jq_or_cat() { command -v jq >/dev/null && jq "$@" || python3 -m json.tool; }

echo "== 1. GET /health =="
curl -s "$API/health"; echo; echo

echo "== 2. GET /flights/search  (BOG -> MDE, 1 pax) =="
BUSQUEDA=$(curl -s "$API/flights/search?origin=BOG&dest=MDE&date=2026-09-10&pax=1")
echo "$BUSQUEDA" | jq_or_cat '.opciones[0]'
INST=$(echo "$BUSQUEDA" | python3 -c 'import sys,json;o=json.load(sys.stdin)["opciones"][0]["tramos"][0];print(o["id_instancia_vuelo"])')
TARIFA=$(echo "$BUSQUEDA" | python3 -c 'import sys,json;o=json.load(sys.stdin)["opciones"][0]["tramos"][0];print(o["tarifa"]["id_tarifa"])')
echo "   -> usare instancia=$INST  tarifa=$TARIFA"
echo

echo "== 3. POST /reservations  (crea la reserva en estado RETENIDA) =="
RESERVA=$(curl -s -X POST "$API/reservations" -H 'Content-Type: application/json' -d "{
  \"segmentos\": [{\"id_instancia_vuelo\": $INST, \"cabina\": \"ECONOMICA\", \"id_tarifa\": $TARIFA}],
  \"pasajeros\": [{\"tipo_documento\": \"CC\", \"numero_documento\": \"1020304050\",
                  \"nombre_completo\": \"Ana Prueba\", \"es_contacto_principal\": true}],
  \"canal\": \"DIRECTO\"
}")
echo "$RESERVA" | jq_or_cat .
COD=$(echo "$RESERVA" | python3 -c 'import sys,json;print(json.load(sys.stdin)["codigo_reserva"])')
echo

echo "== 4. GET /reservations/$COD  (consulta con historial) =="
curl -s "$API/reservations/$COD" | jq_or_cat '{codigo_reserva, estado, iata_origen, iata_destino, monto_total, segmentos, historial}'
echo

echo "== 5. GET /flights/$INST/availability =="
curl -s "$API/flights/$INST/availability"; echo
echo
echo ">> Fin. Abre $API/docs en el navegador para probar interactivamente."
