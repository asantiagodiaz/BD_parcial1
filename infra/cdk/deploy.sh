#!/usr/bin/env bash
# =====================================================================
# Despliegue del Parcial 1 en AWS Academy Learner Lab.
#
#   ./deploy.sh              -> despliega todo
#   ./deploy.sh destroy      -> borra el stack (teardown)
#
# NO usa `cdk bootstrap` ni `cdk deploy` (el Lab prohibe crear los roles IAM
# del toolkit). En su lugar:
#   1. empaqueta el codigo en un tarball y lo sube a un bucket S3 existente
#   2. `cdk synth` genera la plantilla CloudFormation
#   3. `aws cloudformation deploy` la aplica con las credenciales del Lab
#
# Requiere credenciales del Lab activas (AWS_PROFILE o [default]).
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

export AWS_PROFILE="${AWS_PROFILE:-academy}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export CDK_DEFAULT_REGION="$AWS_REGION"
CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export CDK_DEFAULT_ACCOUNT
STACK="AerolineaParcial1"
REPO_ROOT="$(cd ../.. && pwd)"

echo ">> cuenta $CDK_DEFAULT_ACCOUNT  region $AWS_REGION  perfil $AWS_PROFILE"
[ -d node_modules ] || npm install
npx tsc

# ---------- destroy ----------
if [ "${1:-}" = "destroy" ]; then
  aws cloudformation delete-stack --stack-name "$STACK"
  echo ">> esperando a que se borre..."
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" || true
  echo ">> stack borrado. (El bucket de codigo y el par de claves quedan; se van con el Lab.)"
  exit 0
fi

# ---------- limpiar un stack fallido previo ----------
ST="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)"
if [ "$ST" = "ROLLBACK_COMPLETE" ] || [ "$ST" = "ROLLBACK_FAILED" ] || [ "$ST" = "CREATE_FAILED" ]; then
  echo ">> stack previo en $ST -> borrando antes de recrear"
  aws cloudformation delete-stack --stack-name "$STACK"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" || true
fi

# ---------- bucket para el codigo ----------
# Usa un bucket cuyo nombre empiece por 'big-data' si existe; si no, crea uno.
CODE_BUCKET="${CODE_BUCKET:-$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name,'big-data')].Name | [0]" --output text)}"
if [ -z "$CODE_BUCKET" ] || [ "$CODE_BUCKET" = "None" ]; then
  CODE_BUCKET="aerolinea-code-$CDK_DEFAULT_ACCOUNT"
  echo ">> creando bucket $CODE_BUCKET"
  aws s3 mb "s3://$CODE_BUCKET"
fi
echo ">> bucket de codigo: $CODE_BUCKET"

# ---------- empaquetar y subir el codigo ----------
TARBALL="/tmp/aerolinea-code.tgz"
echo ">> empaquetando el repo -> $TARBALL"
tar czf "$TARBALL" -C "$REPO_ROOT" \
  --exclude='.git' \
  --exclude='*/.venv' --exclude='.venv' \
  --exclude='*/node_modules' --exclude='node_modules' \
  --exclude='infra/cdk/cdk.out' \
  --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='*.pdf' --exclude='docs/*.docx' \
  backend etl analytics infra docs
CODE_KEY="code/aerolinea-$(date +%s).tgz"
aws s3 cp "$TARBALL" "s3://$CODE_BUCKET/$CODE_KEY"

# ---------- parametros de acceso ----------
MI_IP="${MI_IP:-$(curl -s https://checkip.amazonaws.com)/32}"
KEY_NAME="${KEY_NAME:-aerolinea-key}"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  echo ">> creando par de claves $KEY_NAME -> $(pwd)/$KEY_NAME.pem"
  aws ec2 create-key-pair --key-name "$KEY_NAME" \
    --query KeyMaterial --output text > "$KEY_NAME.pem"
  chmod 600 "$KEY_NAME.pem"
fi

# ---------- synth + deploy con CloudFormation ----------
echo ">> cdk synth"
npx cdk synth "$STACK" \
  -c codeBucket="$CODE_BUCKET" -c codeKey="$CODE_KEY" \
  -c miIp="$MI_IP" -c keyName="$KEY_NAME" \
  --quiet

echo ">> aws cloudformation deploy  (IP=$MI_IP  keyName=$KEY_NAME)"
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file cdk.out/"$STACK".template.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo
echo ">> outputs:"
aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs[].{Clave:OutputKey,Valor:OutputValue}' --output table

API_URL="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)"

echo
echo ">> esperando a que la API responda (el UserData migra + seed + ETL, ~5-6 min)"
for i in $(seq 1 40); do
  if curl -sf --max-time 5 "$API_URL/health" >/dev/null 2>&1; then
    echo "   API OK: $API_URL"
    break
  fi
  echo "   ...aun no ($i/40)"; sleep 20
done

echo
echo ">> arrancando los crawlers de Glue (la RDS ya tiene el esquema)"
aws glue start-crawler --name crawler-oltp 2>/dev/null || true
aws glue start-crawler --name crawler-olap 2>/dev/null || true

echo
echo "==================================================================="
echo " Verifica:"
echo "   curl $API_URL/health"
echo "   curl \"$API_URL/flights/search?origin=BOG&dest=MDE&date=2026-09-10&pax=1\""
echo "   aws glue get-tables --database-name aerolinea_catalog --query 'TableList[].Name' --output table"
echo " Los crawlers tardan ~3-5 min. Evidencias en docs/evidencia/*-aws.txt"
echo "==================================================================="
