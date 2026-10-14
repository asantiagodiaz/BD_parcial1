#!/usr/bin/env bash
# =====================================================================
# Lanza el job de limpieza en EMR y espera a que termine. El cluster se apaga SOLO
# (--auto-terminate): nunca queda vivo (R10).
#
#   ./run_emr.sh                      -> datos en s3://<bucket>/raw/  -> s3://<bucket>/curated/
#   RAW_PREFIX=raw-test CUR_PREFIX=curated-test ./run_emr.sh   (muestra pequena de prueba)
#   INSTANCES=3 ./run_emr.sh          -> mas nodos (cada m4.large cuenta 4 horas normalizadas por hora)
# =====================================================================
set -euo pipefail
export AWS_PROFILE="${AWS_PROFILE:-academy}" AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${DATA_BUCKET:-p2-airline-$ACCOUNT}"
RAW="${RAW_PREFIX:-raw}"; CUR="${CUR_PREFIX:-curated}"; N="${INSTANCES:-1}"

aws s3 cp "$(cd "$(dirname "$0")/.." && pwd)/emr/job.py" "s3://$BUCKET/code/job.py" --only-show-errors

CID="$(aws emr create-cluster --name "p2-curate-$(date +%H%M)" --release-label emr-7.2.0 \
  --applications Name=Spark --instance-type m4.large --instance-count "$N" --use-default-roles \
  --auto-terminate --log-uri "s3://$BUCKET/emr-logs/" \
  --steps "Type=Spark,Name=curate,ActionOnFailure=TERMINATE_CLUSTER,Args=[--deploy-mode,cluster,--driver-memory,1g,--conf,spark.executor.memory=3g,--conf,spark.executor.cores=2,--conf,spark.executor.instances=1,--conf,spark.dynamicAllocation.enabled=false,s3://$BUCKET/code/job.py,--input,s3://$BUCKET/$RAW,--curated,s3://$BUCKET/$CUR/reservations_curated/,--metrics,s3://$BUCKET/$CUR/route_month_metrics/]" \
  --query ClusterId --output text)"
echo "$CID" > .emr-last
echo ">> cluster $CID lanzado ($N x m4.large, se apaga solo). Esperando..."

last=""
while true; do
  s="$(aws emr describe-cluster --cluster-id "$CID" --query 'Cluster.Status.State' --output text)"
  [ "$s" != "$last" ] && { echo "   $(date +%H:%M:%S) $s"; last="$s"; }
  case "$s" in TERMINATED|TERMINATED_WITH_ERRORS) break;; esac
  sleep 20
done
aws emr describe-cluster --cluster-id "$CID" --query 'Cluster.Status.StateChangeReason.Message' --output text
aws emr list-steps --cluster-id "$CID" --query 'Steps[].[Name,Status.State]' --output text
