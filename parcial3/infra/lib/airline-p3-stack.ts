import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as glue from "aws-cdk-lib/aws-glue";
import * as athena from "aws-cdk-lib/aws-athena";

export interface AirlineP3StackProps extends cdk.StackProps {
  /** Bucket S3 de datos (raw/, ref/, star/, athena-results/, code/). Lo crea deploy.sh. */
  dataBucket: string;
  /** Key del tarball con el codigo dentro de ese bucket. */
  codeKey: string;
  /** Contrasena de PostgreSQL (la genera deploy.sh; no queda en el repo). */
  dbPassword: string;
  /** Nombre del stream de Kinesis (lo crea crear_stream.sh, no este stack). */
  streamName: string;
  /** CIDR autorizado a SSH. Por defecto 0.0.0.0/0. */
  miIp?: string;
  keyName?: string;
}

/**
 * Stack del parcial 3: lo que existe TODO el tiempo (o mientras la EC2 este encendida).
 *
 *   EC2 t3.small -> FastAPI + frontend + PostgreSQL 16 local + hilo consumidor de Kinesis
 *                   + job de refresco de la estrella (lanza consultas Athena)
 *   Glue         -> base airline_star (las tablas las crea el refresco con CTAS)
 *   Athena       -> workgroup con tope de 1 GB por consulta (R10)
 *
 * Lo que existe SOLO mientras se prueba (se cobra por hora) NO esta aqui:
 * Kinesis (1 shard) y Firehose los crean/borran crear_stream.sh y borrar_stream.sh.
 *
 * Reglas del Lab: no crea roles IAM (usa LabRole / LabInstanceProfile), no usa assets de
 * CDK, usa la VPC por defecto y no hay NAT Gateway.
 */
export class AirlineP3Stack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: AirlineP3StackProps) {
    super(scope, id, props);

    const sshCidr = props.miIp ?? "0.0.0.0/0";
    const GLUE_DB = "airline_star";
    const WORKGROUP = "airline-p3";
    const bucket = props.dataBucket;

    const vpc = ec2.Vpc.fromLookup(this, "DefaultVpc", { isDefault: true });

    // ---- Seguridad de red: solo la API es publica; PostgreSQL escucha solo en localhost ----
    const sg = new ec2.SecurityGroup(this, "ApiSg", {
      vpc,
      description: "airline p3 - API publica, SSH desde mi IP",
      allowAllOutbound: true,
      securityGroupName: "airline-p3-sg",
    });
    sg.addIngressRule(ec2.Peer.ipv4(sshCidr), ec2.Port.tcp(22), "SSH desde mi IP");
    sg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(8000), "API + frontend");

    const dbUrl = `postgresql+psycopg://airline:${props.dbPassword}@127.0.0.1:5432/airline`;
    const app = "/opt/airline/parcial3";

    // ---- EC2: PostgreSQL + API ----
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      "set -xe",
      "dnf -y install python3.11 python3.11-pip tar gzip postgresql16-server",
      // PostgreSQL local: solo escucha en 127.0.0.1 y pide contrasena (scram).
      "postgresql-setup --initdb",
      // Primera regla que coincide gana: el usuario airline entra por 127.0.0.1 con contrasena.
      "sed -i '1i host airline airline 127.0.0.1/32 scram-sha-256' /var/lib/pgsql/data/pg_hba.conf",
      "systemctl enable --now postgresql",
      `sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE USER airline WITH PASSWORD '${props.dbPassword}'" || true`,
      `sudo -u postgres psql -c "CREATE DATABASE airline OWNER airline" || true`,
      // Codigo
      "install -d -o ec2-user -g ec2-user /opt/airline",
      `aws s3 cp s3://${bucket}/${props.codeKey} /tmp/app.tgz`,
      "tar xzf /tmp/app.tgz -C /opt/airline",
      "chown -R ec2-user:ec2-user /opt/airline",
      `cat > ${app}/backend/.env <<EOF`,
      `DATABASE_URL=${dbUrl}`,
      "AWS_REGION=us-east-1",
      `KINESIS_STREAM=${props.streamName}`,
      `DATA_BUCKET=${bucket}`,
      `ATHENA_WORKGROUP=${WORKGROUP}`,
      `ATHENA_DATABASE=${GLUE_DB}`,
      `ATHENA_OUTPUT=s3://${bucket}/athena-results/`,
      "EOF",
      `chown ec2-user:ec2-user ${app}/backend/.env`,
      `sudo -u ec2-user bash ${app}/infra/assets/provision-en-ec2.sh > /var/log/airline-provision.log 2>&1 || true`,
      "cat > /etc/systemd/system/airline.service <<EOF",
      "[Unit]",
      "Description=API reservas (FastAPI) + frontend + consumidor Kinesis",
      "After=network-online.target postgresql.service",
      "Requires=postgresql.service",
      "[Service]",
      "User=ec2-user",
      `WorkingDirectory=${app}/backend`,
      // Un solo worker: el consumidor del stream y los contadores viven en este proceso.
      `ExecStart=${app}/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`,
      "Restart=always",
      "[Install]",
      "WantedBy=multi-user.target",
      "EOF",
      "systemctl daemon-reload",
      "systemctl enable --now airline.service"
    );

    const instance = new ec2.Instance(this, "Api", {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
      machineImage: ec2.MachineImage.latestAmazonLinux2023({ cpuType: ec2.AmazonLinuxCpuType.X86_64 }),
      securityGroup: sg,
      userData,
      keyName: props.keyName,
      instanceName: "airline-p3-api",
      blockDevices: [
        {
          deviceName: "/dev/xvda",
          volume: ec2.BlockDeviceVolume.ebs(20, { encrypted: true, volumeType: ec2.EbsDeviceVolumeType.GP3 }),
        },
      ],
    });

    // El Lab prohibe crear roles: se usa LabInstanceProfile (-> LabRole: S3, Athena, Glue, Kinesis).
    instance.node.tryRemoveChild("InstanceProfile");
    instance.node.tryRemoveChild("InstanceRole");
    const cfnInstance = instance.node.defaultChild as ec2.CfnInstance;
    cfnInstance.iamInstanceProfile = "LabInstanceProfile";
    // CDK deja un DependsOn hacia el rol que acabamos de quitar: sin esto CloudFormation falla
    // con "Unresolved resource dependencies [ApiInstanceRole...]".
    cfnInstance.addDeletionOverride("DependsOn");

    // ---- Glue: solo la base. Las 5 tablas de la estrella (y las externas de crudo y referencia)
    // las crea el refresco con CTAS / CREATE EXTERNAL TABLE: asi el esquema vive en un solo lugar
    // (backend/app/star_sql.py) y no se desincroniza con el stack. ----
    new glue.CfnDatabase(this, "GlueDb", {
      catalogId: this.account,
      databaseInput: { name: GLUE_DB, description: "Parcial 3 - modelo estrella de busquedas y reservas" },
    });

    // ---- Athena: workgroup propio con tope de escaneo por consulta (R10) ----
    new athena.CfnWorkGroup(this, "Wg", {
      name: WORKGROUP,
      description: "Modelo estrella del parcial 3 (refresco + preguntas de negocio)",
      recursiveDeleteOption: true,
      workGroupConfiguration: {
        // false: con true Athena rechaza los CTAS con external_location (el refresco escribe
        // cada tabla en star/<tabla>/<run_id>/). El tope de bytes por consulta se aplica igual.
        enforceWorkGroupConfiguration: false,
        publishCloudWatchMetricsEnabled: false,
        bytesScannedCutoffPerQuery: 1_000_000_000, // 1 GB (R10): freno de costo
        resultConfiguration: { outputLocation: `s3://${bucket}/athena-results/` },
      },
    });

    // ---- Salidas ----
    new cdk.CfnOutput(this, "ApiUrl", {
      value: `http://${instance.instancePublicIp}:8000`,
      description: "backend.base_url del harness",
    });
    new cdk.CfnOutput(this, "SshCommand", {
      value: props.keyName ? `ssh -i ${props.keyName}.pem ec2-user@${instance.instancePublicIp}` : "(sin keyName)",
    });
    new cdk.CfnOutput(this, "GlueDatabase", { value: GLUE_DB });
    new cdk.CfnOutput(this, "AthenaWorkgroup", { value: WORKGROUP });
  }
}
