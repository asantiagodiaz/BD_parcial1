#!/usr/bin/env bash
# Borra Firehose y el stream de Kinesis (lo que se cobra por hora). La landing zone en S3,
# la estrella y el resto del stack se conservan: la siguiente sesion empieza con ./crear_stream.sh.
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-east-1}"
STREAM="${STREAM_NAME:-airline-events}"
FIREHOSE="${FIREHOSE_NAME:-airline-events-to-s3}"

if aws firehose describe-delivery-stream --delivery-stream-name "$FIREHOSE" >/dev/null 2>&1; then
  echo ">> borrando Firehose $FIREHOSE"
  aws firehose delete-delivery-stream --delivery-stream-name "$FIREHOSE"
fi
if aws kinesis describe-stream-summary --stream-name "$STREAM" >/dev/null 2>&1; then
  echo ">> borrando stream $STREAM"
  aws kinesis delete-stream --stream-name "$STREAM" --enforce-consumer-deletion
  aws kinesis wait stream-not-exists --stream-name "$STREAM"
fi
echo ">> listo: no queda ningun shard cobrando"
