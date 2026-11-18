#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AirlineP3Stack } from "../lib/airline-p3-stack";

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

new AirlineP3Stack(app, "AirlineP3", {
  env,
  description:
    "Parcial 3 Big Data - EC2 (API + PostgreSQL + consumidor Kinesis) + Glue + Athena. Kinesis y Firehose se crean aparte con crear_stream.sh",
  dataBucket: need("dataBucket"),
  codeKey: need("codeKey"),
  dbPassword: need("dbPassword"),
  streamName: need("streamName"),
  miIp: app.node.tryGetContext("miIp"),
  keyName: app.node.tryGetContext("keyName"),
  // El Lab no tiene bootstrap de CDK: se despliega con `aws cloudformation deploy`.
  synthesizer: new cdk.DefaultStackSynthesizer({ generateBootstrapVersionRule: false }),
});
