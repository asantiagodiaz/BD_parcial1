#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AirlineP2Stack } from "../lib/airline-p2-stack";

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || "us-east-1",
};

// deploy.sh pasa estos valores por contexto (-c clave=valor)
const need = (k: string): string => {
  const v = app.node.tryGetContext(k);
  if (!v) throw new Error(`Falta -c ${k}=... (lo pone deploy.sh automaticamente)`);
  return String(v);
};

new AirlineP2Stack(app, "AirlineP2", {
  env,
  description:
    "Parcial 2 Big Data - panel gerencial: EC2 (API+frontend) + RDS PostgreSQL + S3 + Glue Data Catalog + Athena (EMR se lanza aparte con run_emr.sh)",
  dataBucket: need("dataBucket"),
  codeKey: need("codeKey"),
  dbPassword: need("dbPassword"),
  miIp: app.node.tryGetContext("miIp"),
  keyName: app.node.tryGetContext("keyName"),
  // El Lab no tiene bootstrap de CDK: se despliega con `aws cloudformation deploy`.
  synthesizer: new cdk.DefaultStackSynthesizer({ generateBootstrapVersionRule: false }),
});
