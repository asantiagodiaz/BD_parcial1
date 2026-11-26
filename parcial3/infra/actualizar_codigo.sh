#!/usr/bin/env bash
# Sube el codigo actual (backend, frontend compilado, ref/) a la EC2 ya desplegada y reinicia la
# API, SIN tocar el stack. Redesplegar el stack cambiaria el UserData y CloudFormation
# reiniciaria la instancia (nueva IP publica, PostgreSQL vacio).
#   ./actualizar_codigo.sh            -> backend + ref
#   ./actualizar_codigo.sh --front    -> ademas compila y sube el frontend
set -euo pipefail
cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"
# IP actual de la EC2 (la salida ApiUrl del stack queda vieja si el Lab reinicia la instancia)
IP="$(aws ec2 describe-instances --filters Name=tag:aws:cloudformation:stack-name,Values=AirlineP3 Name=instance-state-name,Values=running --query "Reservations[0].Instances[0].PublicIpAddress" --output text)"
KEY="${KEY_NAME:-airline-p3-key}.pem"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "ec2-user@$IP")

if [ "${1:-}" = "--front" ]; then
  ( cd "$REPO_ROOT/parcial3/frontend" && npm run build --silent )
fi
echo ">> subiendo codigo a $IP"
tar czf - -C "$REPO_ROOT" --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
  --exclude='.pytest_cache' parcial3/backend/app parcial3/backend/requirements.txt parcial3/ref parcial3/frontend/dist \
  | "${SSH[@]}" "tar xzf - -C /opt/airline && cd /opt/airline/parcial3/backend && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart airline"
for i in $(seq 1 20); do
  if curl -sf --max-time 3 "http://$IP:8000/health" >/dev/null; then echo ">> API OK: http://$IP:8000"; exit 0; fi
  sleep 2
done
echo ">> la API no respondio; revisar: ${SSH[*]} sudo journalctl -u airline -n 50" >&2
exit 1
