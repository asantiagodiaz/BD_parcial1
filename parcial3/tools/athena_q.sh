# Uso:  source parcial3/aws-env.sh && source parcial3/tools/athena_q.sh
#       q "SELECT count(*) FROM fact_search"
# Ejecuta una consulta en Athena (workgroup airline-p3, base airline_star), espera el resultado,
# lo imprime como tabla y muestra los bytes escaneados (lo que se cobra y lo que mide R10).
q() {
  local id st
  id=$(aws athena start-query-execution --work-group airline-p3 \
        --query-execution-context Database=airline_star --query-string "$1" \
        --query QueryExecutionId --output text) || return 1
  while st=$(aws athena get-query-execution --query-execution-id "$id" \
        --query QueryExecution.Status.State --output text); [ "$st" = QUEUED ] || [ "$st" = RUNNING ]; do sleep 1; done
  if [ "$st" != SUCCEEDED ]; then
    aws athena get-query-execution --query-execution-id "$id" \
      --query QueryExecution.Status.StateChangeReason --output text
    return 1
  fi
  aws athena get-query-results --query-execution-id "$id" --output json | python3 -c '
import json, sys
for r in json.load(sys.stdin)["ResultSet"]["Rows"]:
    print(" | ".join(c.get("VarCharValue", "") for c in r["Data"]))'
  echo "(escaneado: $(aws athena get-query-execution --query-execution-id "$id" \
        --query QueryExecution.Statistics.DataScannedInBytes --output text) bytes)"
}
