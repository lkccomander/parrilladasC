import { defineRailway, github, postgres, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "us-east4-eqdc4a" });
  Postgres.deploy = { sleepApplication: true };
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const postgresVolume = volume("postgres-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "us-east4-eqdc4a",
    sizeMB: 50000,
  });
  // Preserve the public domain and existing service name for Admin.
  const web = service("web", {
    source: github("lkccomander/parrilladasC"),
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
      watchPatterns: ["/backend/**", "/Dockerfile", "/.dockerignore"],
    },
    healthcheck: "/health/ready",
    healthcheckTimeout: 120,
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: {
      limitOverride: { containers: { cpu: 1, memoryBytes: 536870912 } },
      restartPolicyMaxRetries: 3,
      sleepApplication: true,
    },
  });
  const api = service("api", {
    source: github("lkccomander/parrilladasC"),
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
      watchPatterns: ["/backend/**", "/Dockerfile", "/.dockerignore"],
    },
    healthcheck: "/health/ready",
    healthcheckTimeout: 120,
    preDeploy: "alembic upgrade head",
    networking: { privateNetworkEndpoint: "api" },
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: {
      limitOverride: { containers: { cpu: 1, memoryBytes: 536870912 } },
      restartPolicyMaxRetries: 3,
      sleepApplication: false,
    },
  });

  return project("parrilladasC", {
    variables: { managed: false },
    resources: [Postgres, web, api, postgresVolume],
  });
});
