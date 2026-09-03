#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AerolineaStack } from "../lib/aerolinea-stack";

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || "us-east-1",
};

// deploy.sh pasa estos por contexto:
//   -c codeBucket=<bucket del Lab>  -c codeKey=<key del tarball>
//   -c miIp=<x.x.x.x>/32            -c keyName=aerolinea-key
const codeBucket = app.node.tryGetContext("codeBucket");
const codeKey = app.node.tryGetContext("codeKey");
if (!codeBucket || !codeKey) {
  throw new Error(
    "Faltan -c codeBucket=... y -c codeKey=... (los pone deploy.sh automaticamente)"
  );
}

new AerolineaStack(app, "AerolineaParcial1", {
  env,
  description:
    "Parcial 1 Big Data - reservas aereas: VPC default + SG + 2x RDS PostgreSQL + EC2 API + Glue Data Catalog",
  codeBucket,
  codeKey,
  miIp: app.node.tryGetContext("miIp"),
  keyName: app.node.tryGetContext("keyName"),
  // El Lab no tiene el bootstrap del CDK: se despliega con `aws cloudformation
  // deploy`. Sin synthesizer que dependa de recursos del toolkit ni regla de
  // version de bootstrap.
  synthesizer: new cdk.DefaultStackSynthesizer({
    generateBootstrapVersionRule: false,
  }),
});
