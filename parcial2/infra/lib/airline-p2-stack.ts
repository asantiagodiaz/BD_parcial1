import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";
import * as glue from "aws-cdk-lib/aws-glue";
import * as athena from "aws-cdk-lib/aws-athena";

export interface AirlineP2StackProps extends cdk.StackProps {
  /** Bucket S3 de datos (raw/, curated/, athena-results/, code/). Lo crea deploy.sh; el stack solo lo referencia. */
  dataBucket: string;
  /** Key del tarball con el codigo dentro de ese bucket. */
  codeKey: string;
  /** Contrasena de la RDS (la genera deploy.sh; no queda en el repo). */
  dbPassword: string;
  /** CIDR autorizado a SSH. Por defecto 0.0.0.0/0. */
  miIp?: string;
  keyName?: string;
}

/**
 * Stack del parcial 2, pensado para AWS Academy Learner Lab y para el menor costo
 * que cumple los requisitos (R11/R12):
 *
 *   EC2 t3.small  -> FastAPI + frontend estatico (un solo proceso)
 *   RDS t3.micro  -> PostgreSQL de reservas, 1 AZ, privada (solo la EC2 entra)
 *   S3            -> crudo, curado (Parquet) y resultados de Athena
 *   Glue          -> base + 2 tablas (partition projection, sin crawlers)
 *   Athena        -> workgroup con tope de bytes escaneados
 *   EMR           -> NO esta en el stack: run_emr.sh lanza un cluster efimero
 *                    (--auto-terminate) para que nunca quede vivo (R10).
 *
 * Reglas del Lab: no crea roles IAM (usa LabRole / LabInstanceProfile), no usa
 * assets de CDK, usa la VPC por defecto y no hay NAT Gateway.
 */
export class AirlineP2Stack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: AirlineP2StackProps) {
    super(scope, id, props);

    const sshCidr = props.miIp ?? "0.0.0.0/0";
    const DB_NAME = "airline";
    const DB_USER = "airline";
    const GLUE_DB = "airline_analytics";
    const bucket = props.dataBucket;

    const vpc = ec2.Vpc.fromLookup(this, "DefaultVpc", { isDefault: true });

    // ---- Seguridad de red ----
    const sg = new ec2.SecurityGroup(this, "ApiSg", {
      vpc,
      description: "airline p2 - API publica, SSH desde mi IP, RDS solo interna",
      allowAllOutbound: true,
      securityGroupName: "airline-p2-sg",
    });
    sg.addIngressRule(ec2.Peer.ipv4(sshCidr), ec2.Port.tcp(22), "SSH desde mi IP");
    // La API debe estar accesible para el harness del profesor -> publica en 8000.
    sg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(8000), "API + frontend");
    // PostgreSQL (5432) solo entre miembros de este mismo SG (EC2 -> RDS).
    sg.connections.allowInternally(ec2.Port.tcp(5432), "PostgreSQL EC2 -> RDS");

    // ---- RDS PostgreSQL (R11: 1 AZ, clase pequena) ----
    const db = new rds.DatabaseInstance(this, "Db", {
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16 }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [sg],
      credentials: rds.Credentials.fromPassword(DB_USER, cdk.SecretValue.unsafePlainText(props.dbPassword)),
      databaseName: DB_NAME,
      allocatedStorage: 20,
      storageEncrypted: true,
      multiAz: false,
      publiclyAccessible: false,
      backupRetention: cdk.Duration.days(1),
      deleteAutomatedBackups: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      instanceIdentifier: "airline-p2-db",
    });

    const dbUrl =
      `postgresql+psycopg://${DB_USER}:${props.dbPassword}@${db.dbInstanceEndpointAddress}:5432/${DB_NAME}`;

    // ---- EC2 con API + frontend ----
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      "set -xe",
      "dnf -y install python3.11 python3.11-pip tar gzip",
      "install -d -o ec2-user -g ec2-user /opt/airline",
      `aws s3 cp s3://${bucket}/${props.codeKey} /tmp/app.tgz`,
      "tar xzf /tmp/app.tgz -C /opt/airline",
      "chown -R ec2-user:ec2-user /opt/airline",
      "cat > /opt/airline/parcial2/backend/.env <<EOF",
      `DATABASE_URL=${dbUrl}`,
      "AWS_REGION=us-east-1",
      "ATHENA_WORKGROUP=airline-wg",
      `ATHENA_DATABASE=${GLUE_DB}`,
      `ATHENA_OUTPUT=s3://${bucket}/athena-results/`,
      "EOF",
      "chown ec2-user:ec2-user /opt/airline/parcial2/backend/.env",
      "sudo -u ec2-user bash /opt/airline/parcial2/infra/assets/provision-en-ec2.sh > /var/log/airline-provision.log 2>&1 || true",
      "cat > /etc/systemd/system/airline.service <<EOF",
      "[Unit]",
      "Description=API reservas (FastAPI) + frontend",
      "After=network-online.target",
      "[Service]",
      "User=ec2-user",
      "WorkingDirectory=/opt/airline/parcial2/backend",
      "ExecStart=/opt/airline/parcial2/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000",
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
      instanceName: "airline-p2-api",
      blockDevices: [
        {
          deviceName: "/dev/xvda",
          volume: ec2.BlockDeviceVolume.ebs(20, { encrypted: true, volumeType: ec2.EbsDeviceVolumeType.GP3 }),
        },
      ],
    });

    // El Lab prohibe crear roles: se quita el rol/profile que CDK genera y se usa
    // LabInstanceProfile (-> LabRole, con permisos de S3, Athena y Glue).
    instance.node.tryRemoveChild("InstanceProfile");
    instance.node.tryRemoveChild("InstanceRole");
    const cfnInstance = instance.node.defaultChild as ec2.CfnInstance;
    cfnInstance.iamInstanceProfile = "LabInstanceProfile";
    cfnInstance.addOverride("DependsOn", [(db.node.defaultChild as rds.CfnDBInstance).logicalId]);

    // ---- Glue Data Catalog: base + 2 tablas (sin crawlers: el esquema es fijo y conocido) ----
    const glueDb = new glue.CfnDatabase(this, "GlueDb", {
      catalogId: this.account,
      databaseInput: { name: GLUE_DB, description: "Parcial 2 - historial de reservas curado (EMR) y metricas" },
    });

    const parquet = (location: string) => ({
      location,
      inputFormat: "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
      outputFormat: "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
      serdeInfo: {
        serializationLibrary: "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
        parameters: { "serialization.format": "1" },
      },
    });

    const detailLocation = `s3://${bucket}/curated/reservations_curated/`;
    const detail = new glue.CfnTable(this, "TableDetail", {
      catalogId: this.account,
      databaseName: GLUE_DB,
      tableInput: {
        name: "reservations_curated",
        tableType: "EXTERNAL_TABLE",
        parameters: {
          classification: "parquet",
          EXTERNAL: "TRUE",
          // Partition projection: Athena calcula las 24 particiones (2023-01..2024-12)
          // sin MSCK REPAIR ni crawler; consulta por mes = lee 1 prefijo.
          "projection.enabled": "true",
          "projection.month.type": "date",
          "projection.month.format": "yyyy-MM",
          "projection.month.range": "2023-01,2024-12",
          "projection.month.interval": "1",
          "projection.month.interval.unit": "MONTHS",
          "storage.location.template": `${detailLocation}month=\${month}/`,
        },
        partitionKeys: [{ name: "month", type: "string" }],
        storageDescriptor: {
          columns: [
            { name: "reservation_id", type: "string" },
            { name: "flight_id", type: "string" },
            { name: "route", type: "string" },
            { name: "fare_class", type: "string" },
            { name: "price_cents", type: "bigint" },
            { name: "status", type: "string" },
          ],
          ...parquet(detailLocation),
        },
      },
    });
    detail.addDependency(glueDb);

    const metrics = new glue.CfnTable(this, "TableMetrics", {
      catalogId: this.account,
      databaseName: GLUE_DB,
      tableInput: {
        name: "route_month_metrics",
        tableType: "EXTERNAL_TABLE",
        parameters: { classification: "parquet", EXTERNAL: "TRUE" },
        storageDescriptor: {
          columns: [
            { name: "route", type: "string" },
            { name: "month", type: "string" },
            { name: "seats_capacity", type: "bigint" },
            { name: "seats_sold", type: "bigint" },
            { name: "occupancy", type: "double" },
            { name: "revenue_cents", type: "bigint" },
            { name: "bookings", type: "bigint" },
            { name: "cancellations", type: "bigint" },
          ],
          ...parquet(`s3://${bucket}/curated/route_month_metrics/`),
        },
      },
    });
    metrics.addDependency(glueDb);

    // ---- Athena: workgroup propio con tope de escaneo por consulta ----
    new athena.CfnWorkGroup(this, "Wg", {
      name: "airline-wg",
      description: "Consultas del panel gerencial (R6/R7)",
      recursiveDeleteOption: true,
      workGroupConfiguration: {
        enforceWorkGroupConfiguration: true,
        publishCloudWatchMetricsEnabled: false,
        bytesScannedCutoffPerQuery: 1_000_000_000, // 1 GB: freno de costo ante un SELECT mal hecho
        resultConfiguration: { outputLocation: `s3://${bucket}/athena-results/` },
      },
    });

    // ---- Salidas ----
    new cdk.CfnOutput(this, "ApiUrl", {
      value: `http://${instance.instancePublicIp}:8000`,
      description: "URL de la API y del frontend (backend.base_url y frontend.base_url del harness)",
    });
    new cdk.CfnOutput(this, "SshCommand", {
      value: props.keyName ? `ssh -i ${props.keyName}.pem ec2-user@${instance.instancePublicIp}` : "(sin keyName)",
    });
    new cdk.CfnOutput(this, "DbEndpoint", { value: db.dbInstanceEndpointAddress });
    new cdk.CfnOutput(this, "GlueDatabase", { value: GLUE_DB });
    new cdk.CfnOutput(this, "AthenaWorkgroup", { value: "airline-wg" });
  }
}
