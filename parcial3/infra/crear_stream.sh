#!/usr/bin/env bash
# =====================================================================
# Crea lo que se cobra por hora y solo debe existir MIENTRAS SE PRUEBA:
#   * Kinesis Data Stream: modo PROVISIONADO, 1 shard, retencion 24 h, sin
#     enhanced fan-out (R11). ~US$0,015 por hora.
#   * Firehose: lee el stream y entrega a la landing zone s3://BUCKET/raw/events/
#     (bufer 60 s, gzip, un evento por linea) (R4).
# Borrar con ./borrar_stream.sh al terminar la sesion.
# Usa LabRole (el Lab no deja crear roles).
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"
export AWS_REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${DATA_BUCKET:-p3-airline-$ACCOUNT}"
STREAM="${STREAM_NAME:-airline-events}"
FIREHOSE="${FIREHOSE_NAME:-airline-events-to-s3}"
ROLE_ARN="arn:aws:iam::$ACCOUNT:role/LabRole"

# ---------- Kinesis ----------
if aws kinesis describe-stream-summary --stream-name "$STREAM" >/dev/null 2>&1; then
  echo ">> el stream $STREAM ya existe"
else
  echo ">> creando stream $STREAM (provisionado, 1 shard)"
  aws kinesis create-stream --stream-name "$STREAM" --shard-count 1 \
    --stream-mode-details StreamMode=PROVISIONED
fi
aws kinesis wait stream-exists --stream-name "$STREAM"
STREAM_ARN="$(aws kinesis describe-stream-summary --stream-name "$STREAM" \
  --query StreamDescriptionSummary.StreamARN --output text)"
aws kinesis describe-stream-summary --stream-name "$STREAM" --query \
  'StreamDescriptionSummary.{modo:StreamModeDetails.StreamMode,shards:OpenShardCount,retencion_h:RetentionPeriodHours,estado:StreamStatus}' \
  --output table

# ---------- Firehose ----------
if aws firehose describe-delivery-stream --delivery-stream-name "$FIREHOSE" >/dev/null 2>&1; then
  echo ">> Firehose $FIREHOSE ya existe"
else
  echo ">> creando Firehose $FIREHOSE -> s3://$BUCKET/raw/events/"
  # AppendDelimiterToRecord: agrega "\n" a cada registro. Sin esto Firehose concatena los
  # JSON ("}{") y la SerDe JSON de Athena no puede leerlos (lee un objeto por linea).
  aws firehose create-delivery-stream \
    --delivery-stream-name "$FIREHOSE" \
    --delivery-stream-type KinesisStreamAsSource \
    --kinesis-stream-source-configuration "KinesisStreamARN=$STREAM_ARN,RoleARN=$ROLE_ARN" \
    --extended-s3-destination-configuration "{
      \"RoleARN\": \"$ROLE_ARN\",
      \"BucketARN\": \"arn:aws:s3:::$BUCKET\",
      \"Prefix\": \"raw/events/\",
      \"ErrorOutputPrefix\": \"raw/errors/!{firehose:error-output-type}/\",
      \"BufferingHints\": {\"SizeInMBs\": 5, \"IntervalInSeconds\": 60},
      \"CompressionFormat\": \"GZIP\",
      \"ProcessingConfiguration\": {
        \"Enabled\": true,
        \"Processors\": [{\"Type\": \"AppendDelimiterToRecord\", \"Parameters\": [{\"ParameterName\": \"Delimiter\", \"ParameterValue\": \"\\\\n\"}]}]
      },
      \"CloudWatchLoggingOptions\": {\"Enabled\": false}
    }"
fi
echo ">> esperando a que Firehose quede ACTIVE"
for i in $(seq 1 40); do
  S="$(aws firehose describe-delivery-stream --delivery-stream-name "$FIREHOSE" \
    --query DeliveryStreamDescription.DeliveryStreamStatus --output text)"
  [ "$S" = "ACTIVE" ] && break
  echo "   $S ($i/40)"; sleep 10
done
echo ">> listo. stream=$STREAM  landing zone=s3://$BUCKET/raw/events/"
echo ">> AL TERMINAR: ./borrar_stream.sh  (el shard se cobra por hora)"
