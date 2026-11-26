#!/usr/bin/env bash
# Demo para la defensa: sigue UN evento por todo el camino (bloque R1-R4).
#   API (busqueda + reserva + cancelacion) -> Kinesis -> vista en vivo -> Firehose -> S3
#
# Uso (desde la raiz del repo, con el stream creado):
#   source parcial3/aws-env.sh
#   parcial3/tools/demo_evento.sh                 # pausa entre pasos (Enter para seguir)
#   SIN_PAUSA=1 parcial3/tools/demo_evento.sh
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-east-1}"
STREAM="${STREAM_NAME:-airline-events}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
B="s3://${DATA_BUCKET:-p3-airline-$ACCOUNT}"
# IP actual de la EC2 (la salida ApiUrl del stack queda vieja si el Lab reinicia la instancia)
API="${API:-http://$(aws ec2 describe-instances --filters Name=tag:aws:cloudformation:stack-name,Values=AirlineP3 Name=instance-state-name,Values=running --query "Reservations[0].Instances[0].PublicIpAddress" --output text):8000}"
SUF="$(date +%H%M%S)"
VUELO="DEMO-$SUF"
SESION="demo-sesion-$SUF"
INICIO="$(date +%s)"

paso() { echo; echo "════ $* ════"; [ -n "${SIN_PAUSA:-}" ] || read -rp "(Enter) " _; }
vivo() { curl -s "$API/analytics/live?window=5" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("   en vivo (5 min): búsquedas=%(searches)s  reservas=%(reservations)s  cancelaciones=%(cancellations)s" % d)'; }

echo "API: $API   stream: $STREAM   landing zone: $B/raw/events/"
paso "0. Vista en vivo ANTES"
vivo

paso "1. Acciones en la API (vuelo $VUELO, sesión $SESION)"
curl -s -o /dev/null -X POST "$API/admin/flights" -H 'Content-Type: application/json' \
  -d "{\"flight_id\":\"$VUELO\",\"route\":\"CTG-BOG\",\"flight_date\":\"2026-12-20\",\"capacity\":5,\"price_cents\":250000}"
echo "-> GET /flights/search (con X-Session-Id)"
curl -s -H "X-Session-Id: $SESION" "$API/flights/search?origin=CTG&destination=BOG&date=2026-12-20" \
  | python3 -c 'import json,sys; print("   ", len(json.load(sys.stdin)), "vuelos encontrados")'
echo "-> POST /reservations"
RES="$(curl -s -X POST "$API/reservations" -H 'Content-Type: application/json' \
  -d "{\"flight_id\":\"$VUELO\",\"passenger_name\":\"Pasajera Demo\",\"fare_class\":\"BUSINESS\"}")"
echo "    $RES"
RID="$(echo "$RES" | python3 -c 'import json,sys; print(json.load(sys.stdin)["reservation_id"])')"
echo "-> POST /reservations/$RID/cancel"
echo "    $(curl -s -X POST "$API/reservations/$RID/cancel")"
echo "-> cancelar otra vez (debe dar 409): $(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/reservations/$RID/cancel")"

paso "2. Los eventos en Kinesis (lo que publicó la API; fíjense: sin nombre del pasajero)"
sleep 2
IT="$(aws kinesis get-shard-iterator --stream-name "$STREAM" --shard-id shardId-000000000000 \
  --shard-iterator-type AT_TIMESTAMP --timestamp "$INICIO" --query ShardIterator --output text)"
IDS="$(aws kinesis get-records --shard-iterator "$IT" --limit 1000 --output json | python3 -c '
import base64, json, sys
sesion, vuelo = sys.argv[1], sys.argv[2]
ids = []
for r in json.load(sys.stdin)["Records"]:
    e = json.loads(base64.b64decode(r["Data"]))
    if e.get("session_id") == sesion or e.get("flight_id") == vuelo:
        print("   clave de partición:", r["PartitionKey"], file=sys.stderr)
        print(json.dumps(e, indent=2, ensure_ascii=False), file=sys.stderr)
        ids.append(e["event_id"])
print(" ".join(ids))' "$SESION" "$VUELO")"
echo "event_id publicados: $IDS"

paso "3. Vista en vivo DESPUÉS (la alimenta el hilo consumidor del stream, no Athena)"
vivo

paso "4. Landing zone en S3 (Firehose entrega cada ~60 s; esperando los 3 eventos)"
for i in $(seq 1 24); do
  ENCONTRADOS=0
  for k in $(aws s3api list-objects-v2 --bucket "${B#s3://}" --prefix "raw/events/$(date -u +%Y/%m/%d)/" \
      --query "Contents[?LastModified>='$(date -u -d "@$INICIO" +%Y-%m-%dT%H:%M:%S)'].Key" --output text); do
    [ "$k" = "None" ] && continue
    for id in $IDS; do
      aws s3 cp "$B/$k" - 2>/dev/null | gunzip | grep -q "$id" && { echo "   $id -> $B/$k"; ENCONTRADOS=$((ENCONTRADOS+1)); }
    done
  done
  [ "$ENCONTRADOS" -ge "$(echo $IDS | wc -w)" ] && { echo "   listo en $(( $(date +%s) - INICIO )) s (límite R4: 300 s)"; break; }
  echo "   ...aún no ($(( $(date +%s) - INICIO )) s)"; sleep 10
done

echo
echo "Siguiente paso (bloque R5-R10): POST /admin/refresh-star y consultar en Athena."
