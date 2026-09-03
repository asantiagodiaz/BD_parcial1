#!/usr/bin/env bash
# Reautoriza el security group aerolinea-sg con tu IP publica actual.
# Util cuando el Lab (o tu red) te cambia la IP entre sesiones.
set -euo pipefail
export AWS_PROFILE="${AWS_PROFILE:-academy}"
SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=aerolinea-sg \
  --query 'SecurityGroups[0].GroupId' --output text)
IP="$(curl -s https://checkip.amazonaws.com)/32"
echo ">> SG=$SG   tu IP ahora: $IP"
for p in 22 8000 5432; do
  aws ec2 authorize-security-group-ingress --group-id "$SG" \
    --protocol tcp --port "$p" --cidr "$IP" 2>/dev/null \
    && echo "   + $p abierto para $IP" \
    || echo "   $p ya estaba abierto para $IP"
done
echo ">> listo. Reintenta:  ./validar.sh"
