import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";
import * as glue from "aws-cdk-lib/aws-glue";

export interface AerolineaStackProps extends cdk.StackProps {
  /** CIDR autorizado a SSH (22), API (8000) y psql (5432). Por defecto 0.0.0.0/0. */
  miIp?: string;
  /** Par de claves EC2 existente para poder entrar por SSH (opcional). */
  keyName?: string;
  /** Bucket S3 (del Lab) donde deploy.sh sube el tarball con el codigo. */
  codeBucket: string;
  /** Key del tarball dentro de ese bucket. */
  codeKey: string;
}

/**
 * Stack unico con toda la infra del parcial, pensado para AWS Academy Learner Lab.
 *
 * El Lab NO permite crear roles IAM (ni los del CDK bootstrap), por eso:
 *  - Este stack no crea ningun rol ni instance profile: usa los preexistentes
 *    `LabRole` / `LabInstanceProfile`.
 *  - No usa assets de CDK (que requieren el bucket del bootstrap). El codigo se
 *    sube a un bucket existente del Lab con deploy.sh y aqui solo se referencia.
 *  - Se despliega con `cdk synth` + `aws cloudformation deploy` (sin `cdk deploy`).
 *
 * Usa la VPC por defecto (el Lab no deja crear NAT gateways / EIPs). Las RDS son
 * `publiclyAccessible` para que el crawler de Glue y tu `psql` las alcancen; el
 * acceso real lo cierra el security group.
 */
export class AerolineaStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: AerolineaStackProps) {
    super(scope, id, props);

    const ingressCidr = props.miIp ?? "0.0.0.0/0";
    const DB_NAME = "aerolinea";
    const DB_USER = "aerolinea";
    // Credencial fija para el parcial (NFR-07 exige cifrado en reposo/transito,
    // no rotacion). En un entorno real seria un Secret rotado.
    const DB_PASS = "aerolinea123";

    // ---- VPC por defecto del Lab ----
    const vpc = ec2.Vpc.fromLookup(this, "DefaultVpc", { isDefault: true });

    // ---- Security group compartido: EC2 <-> RDS <-> Glue ----
    const sg = new ec2.SecurityGroup(this, "AerolineaSg", {
      vpc,
      description: "aerolinea parcial1 - API + RDS + Glue",
      allowAllOutbound: true,
      securityGroupName: "aerolinea-sg",
    });
    sg.addIngressRule(ec2.Peer.ipv4(ingressCidr), ec2.Port.tcp(22), "SSH");
    sg.addIngressRule(ec2.Peer.ipv4(ingressCidr), ec2.Port.tcp(8000), "API FastAPI");
    // Glue exige un SG con una regla self-referencing que abra TODOS los puertos
    // (asi los ENI del crawler se hablan entre si). El trafico externo sigue
    // limitado: esta regla solo aplica a origen = el propio SG.
    sg.connections.allowInternally(ec2.Port.allTraffic(), "Glue self-ref + PostgreSQL interno");
    // ...y 5432 desde tu IP, para inspeccionar las bases con psql durante la defensa
    sg.addIngressRule(ec2.Peer.ipv4(ingressCidr), ec2.Port.tcp(5432), "psql desde mi maquina");

    const dbCreds = rds.Credentials.fromPassword(
      DB_USER,
      cdk.SecretValue.unsafePlainText(DB_PASS)
    );

    const mkDb = (name: string): rds.DatabaseInstance =>
      new rds.DatabaseInstance(this, name, {
        engine: rds.DatabaseInstanceEngine.postgres({
          // El Learner Lab solo ofrece 16.9+; usamos la version mayor y RDS
          // elige la minor disponible mas reciente.
          version: rds.PostgresEngineVersion.VER_16,
        }),
        instanceType: ec2.InstanceType.of(
          ec2.InstanceClass.T3,
          ec2.InstanceSize.MICRO
        ),
        vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
        securityGroups: [sg],
        credentials: dbCreds,
        databaseName: DB_NAME,
        allocatedStorage: 20,
        storageEncrypted: true, // NFR-07
        multiAz: false,
        publiclyAccessible: true,
        backupRetention: cdk.Duration.days(1),
        deleteAutomatedBackups: true,
        removalPolicy: cdk.RemovalPolicy.DESTROY, // Lab: se destruye al terminar
        instanceIdentifier: name.toLowerCase(),
      });

    const oltp = mkDb("aerolinea-oltp");
    const olap = mkDb("aerolinea-olap");

    const oltpUrl = `postgresql+psycopg://${DB_USER}:${DB_PASS}@${oltp.dbInstanceEndpointAddress}:5432/${DB_NAME}`;
    const olapUrl = `postgresql+psycopg://${DB_USER}:${DB_PASS}@${olap.dbInstanceEndpointAddress}:5432/${DB_NAME}`;

    // ---- EC2 con la API ----
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      "set -xe",
      "dnf -y install python3.11 python3.11-pip tar gzip",
      "install -d -o ec2-user -g ec2-user /opt/aerolinea",
      `aws s3 cp s3://${props.codeBucket}/${props.codeKey} /tmp/app.tgz`,
      "tar xzf /tmp/app.tgz -C /opt/aerolinea",
      "chown -R ec2-user:ec2-user /opt/aerolinea",
      "cat > /opt/aerolinea/backend/.env <<EOF",
      `OLTP_DATABASE_URL=${oltpUrl}`,
      `OLAP_DATABASE_URL=${olapUrl}`,
      "HOLD_MINUTES=15",
      "MIN_CONNECTION_MINUTES=45",
      "MAX_CONNECTION_MINUTES=360",
      "EOF",
      "chown ec2-user:ec2-user /opt/aerolinea/backend/.env",
      "sudo -u ec2-user bash /opt/aerolinea/infra/cdk/assets/provision-en-ec2.sh > /var/log/aerolinea-provision.log 2>&1 || true",
      "cat > /etc/systemd/system/aerolinea.service <<EOF",
      "[Unit]",
      "Description=API reservas aereas (FastAPI)",
      "After=network-online.target",
      "[Service]",
      "User=ec2-user",
      "WorkingDirectory=/opt/aerolinea/backend",
      "ExecStart=/opt/aerolinea/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000",
      "Restart=always",
      "[Install]",
      "WantedBy=multi-user.target",
      "EOF",
      "systemctl daemon-reload",
      "systemctl enable --now aerolinea.service"
    );

    const ami = ec2.MachineImage.latestAmazonLinux2023({
      cpuType: ec2.AmazonLinuxCpuType.X86_64,
    });

    const ec2Instance = new ec2.Instance(this, "AerolineaApi", {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.SMALL
      ),
      machineImage: ami,
      securityGroup: sg,
      userData,
      keyName: props.keyName,
      instanceName: "aerolinea-api",
      blockDevices: [
        {
          deviceName: "/dev/xvda",
          volume: ec2.BlockDeviceVolume.ebs(20, {
            encrypted: true,
            volumeType: ec2.EbsDeviceVolumeType.GP3,
          }),
        },
      ],
    });
    ec2Instance.node.addDependency(oltp, olap);

    // El Lab prohibe crear roles/instance profiles. CDK crea un rol + instance
    // profile por defecto para toda `ec2.Instance`. Los quitamos de la plantilla
    // y usamos el instance profile preexistente `LabInstanceProfile` (-> LabRole,
    // que ya tiene permisos de S3, RDS, Glue y EC2).
    ec2Instance.node.tryRemoveChild("InstanceProfile");
    ec2Instance.node.tryRemoveChild("InstanceRole");
    const cfnInstance = ec2Instance.node.defaultChild as ec2.CfnInstance;
    cfnInstance.iamInstanceProfile = "LabInstanceProfile";
    // El nodo eliminado dejo un DependsOn colgante; lo reemplazamos por la
    // dependencia real (la EC2 arranca despues de que las RDS esten disponibles).
    cfnInstance.addOverride("DependsOn", [
      (oltp.node.defaultChild as rds.CfnDBInstance).logicalId,
      (olap.node.defaultChild as rds.CfnDBInstance).logicalId,
    ]);

    // ---- Glue Data Catalog: 1 database + 2 conexiones JDBC + 2 crawlers ----
    const glueDbName = "aerolinea_catalog";
    new glue.CfnDatabase(this, "GlueDb", {
      catalogId: this.account,
      databaseInput: {
        name: glueDbName,
        description: "Metadatos OLTP + OLAP - reservas aereas (5.7)",
      },
    });

    const subnetId = vpc.publicSubnets[0].subnetId;
    const az = vpc.publicSubnets[0].availabilityZone;

    const mkConn = (name: string, host: string): glue.CfnConnection =>
      new glue.CfnConnection(this, `Conn-${name}`, {
        catalogId: this.account,
        connectionInput: {
          name,
          connectionType: "JDBC",
          connectionProperties: {
            JDBC_CONNECTION_URL: `jdbc:postgresql://${host}:5432/${DB_NAME}`,
            USERNAME: DB_USER,
            PASSWORD: DB_PASS,
          },
          physicalConnectionRequirements: {
            subnetId,
            availabilityZone: az,
            securityGroupIdList: [sg.securityGroupId],
          },
        },
      });

    const connOltp = mkConn("conn-oltp", oltp.dbInstanceEndpointAddress);
    const connOlap = mkConn("conn-olap", olap.dbInstanceEndpointAddress);

    const mkCrawler = (
      name: string,
      connName: string,
      prefix: string
    ): glue.CfnCrawler =>
      new glue.CfnCrawler(this, `Crawler-${name}`, {
        name,
        // ARN completo: el Lab no deja que Glue asuma un rol por nombre corto
        role: `arn:aws:iam::${this.account}:role/LabRole`,
        databaseName: glueDbName,
        tablePrefix: prefix,
        targets: {
          jdbcTargets: [{ connectionName: connName, path: `${DB_NAME}/public/%` }],
        },
      });

    mkCrawler("crawler-oltp", "conn-oltp", "oltp_").addDependency(connOltp);
    mkCrawler("crawler-olap", "conn-olap", "olap_").addDependency(connOlap);

    // ---- Salidas ----
    new cdk.CfnOutput(this, "ApiUrl", {
      value: `http://${ec2Instance.instancePublicIp}:8000`,
      description: "Base URL de la API (health, /flights/search, /reservations)",
    });
    new cdk.CfnOutput(this, "SshCommand", {
      value: props.keyName
        ? `ssh -i ${props.keyName}.pem ec2-user@${ec2Instance.instancePublicIp}`
        : "(sin keyName)",
    });
    new cdk.CfnOutput(this, "OltpEndpoint", { value: oltp.dbInstanceEndpointAddress });
    new cdk.CfnOutput(this, "OlapEndpoint", { value: olap.dbInstanceEndpointAddress });
    new cdk.CfnOutput(this, "GlueDatabase", { value: glueDbName });
    new cdk.CfnOutput(this, "ArrancarCrawlers", {
      value: `aws glue start-crawler --name crawler-oltp ; aws glue start-crawler --name crawler-olap`,
      description: "Ejecutar tras el deploy para poblar el Data Catalog",
    });
    new cdk.CfnOutput(this, "VerTablasCatalogo", {
      value: `aws glue get-tables --database-name ${glueDbName} --query 'TableList[].Name' --output table`,
    });
  }
}
