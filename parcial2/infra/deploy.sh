#!/usr/bin/env bash
# =====================================================================
# Despliegue del Parcial 2 en AWS Academy Learner Lab.
#
#   ./deploy.sh              -> crea/actualiza todo (EC2 + RDS + S3 + Glue + Athena)
#   ./deploy.sh destroy      -> borra el stack (NO borra el bucket de datos)
#
# No usa `cdk bootstrap` ni `cdk deploy` (el Lab prohibe los roles IAM del toolkit):
# `cdk synth` genera la plantilla y `aws cloudformation deploy` la aplica.
# EMR no esta en el stack: se lanza con ./run_emr.sh.
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

export AWS_PROFILE="${AWS_PROFILE:-academy}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export CDK_DEFAULT_REGION="$AWS_REGION"
CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export CDK_DEFAULT_ACCOUNT
STACK="AirlineP2"
REPO_ROOT="$(cd ../.. && pwd)"
BUCKET="${DATA_BUCKET:-p2-airline-$CDK_DEFAULT_ACCOUNT}"

echo ">> cuenta $CDK_DEFAULT_ACCOUNT  region $AWS_REGION  perfil $AWS_PROFILE  bucket $BUCKET"
[ -d node_modules ] || npm install
npx tsc

if [ "${1:-}" = "destroy" ]; then
  aws cloudformation delete-stack --stack-name "$STACK"
  echo ">> esperando a que se borre..."
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" || true
  echo ">> stack borrado. El bucket s3://$BUCKET y sus datos se conservan (cuestan centavos)."
  exit 0
fi

ST="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)"
if [ "$ST" = "ROLLBACK_COMPLETE" ] || [ "$ST" = "ROLLBACK_FAILED" ] || [ "$ST" = "CREATE_FAILED" ]; then
  echo ">> stack previo en $ST -> borrando antes de recrear"
  aws cloudformation delete-stack --stack-name "$STACK"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" || true
fi

# ---------- bucket de datos (privado) ----------
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo ">> creando bucket $BUCKET"
  aws s3 mb "s3://$BUCKET"
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

# ---------- contrasena de la base (generada una vez, fuera del repo) ----------
[ -f .dbpass ] || { openssl rand -hex 16 > .dbpass; chmod 600 .dbpass; }
DB_PASS="$(cat .dbpass)"

# ---------- empaquetar y subir backend + frontend ----------
TARBALL="/tmp/airline-p2-code.tgz"
tar czf "$TARBALL" -C "$REPO_ROOT" \
  --exclude='.venv' --exclude='node_modules' --exclude='cdk.out' --exclude='__pycache__' --exclude='*.pyc' \
  parcial2/backend parcial2/frontend parcial2/infra/assets
CODE_KEY="code/airline-p2-$(date +%s).tgz"
aws s3 cp "$TARBALL" "s3://$BUCKET/$CODE_KEY" --only-show-errors
aws s3 cp "$REPO_ROOT/parcial2/emr/job.py" "s3://$BUCKET/code/job.py" --only-show-errors

# ---------- acceso ----------
MI_IP="${MI_IP:-$(curl -s https://checkip.amazonaws.com | tr -d '\n')/32}"
KEY_NAME="${KEY_NAME:-airline-p2-key}"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  echo ">> creando par de claves $KEY_NAME -> $(pwd)/$KEY_NAME.pem"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query KeyMaterial --output text > "$KEY_NAME.pem"
  chmod 600 "$KEY_NAME.pem"
fi

echo ">> cdk synth"
npx cdk synth "$STACK" -c dataBucket="$BUCKET" -c codeKey="$CODE_KEY" -c dbPassword="$DB_PASS" \
  -c miIp="$MI_IP" -c keyName="$KEY_NAME" --quiet

echo ">> aws cloudformation deploy  (SSH desde $MI_IP)"
aws cloudformation deploy --stack-name "$STACK" --template-file cdk.out/"$STACK".template.json \
  --no-fail-on-empty-changeset

aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs[].{Clave:OutputKey,Valor:OutputValue}' --output table
API_URL="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)"

echo ">> esperando a que la API responda (instala dependencias; ~4-6 min)"
for i in $(seq 1 40); do
  if curl -sf --max-time 5 "$API_URL/health" >/dev/null 2>&1; then echo "   API OK: $API_URL"; break; fi
  echo "   ...aun no ($i/40)"; sleep 20
done
echo ">> Siguiente: ./run_emr.sh  (limpieza con EMR)  y poner $API_URL en config.yaml del harness"
