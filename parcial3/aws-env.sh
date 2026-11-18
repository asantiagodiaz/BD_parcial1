# Uso:  source parcial3/aws-env.sh
# Activa las credenciales del Learner Lab SOLO en esta terminal y SOLO para este proyecto:
# los comandos aws, deploy.sh, crear_stream.sh y el harness leen estos archivos en lugar de
# ~/.aws. Al cerrar la terminal (o con `deactivate_aws`) todo vuelve a como estaba.
_P3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AWS_SHARED_CREDENTIALS_FILE="$_P3_DIR/aws-credentials"
export AWS_CONFIG_FILE="$_P3_DIR/aws-config"
export AWS_PROFILE=learnerlab
export AWS_REGION=us-east-1
deactivate_aws() { unset AWS_SHARED_CREDENTIALS_FILE AWS_CONFIG_FILE AWS_PROFILE AWS_REGION; unset -f deactivate_aws; }
echo "AWS -> perfil learnerlab del Parcial 3 ($AWS_SHARED_CREDENTIALS_FILE)"
