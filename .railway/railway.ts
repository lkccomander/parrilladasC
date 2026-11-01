import { defineRailway, github, postgres, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "europe-west4-drams3a" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const postgresVolume = volume("postgres-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "europe-west4-drams3a",
    sizeMB: 50000,
  });
  const web = service("web", {
    source: github("lkccomander/parrilladasC"),
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
      watchPatterns: ["/backend/**", "/Dockerfile", "/.dockerignore"],
    },
    preDeploy: "alembic upgrade head",
    healthcheck: "/health/ready",
    healthcheckTimeout: 120,
    deploy: {
      restartPolicyMaxRetries: 3,
      limitOverride: { containers: { cpu: 1, memoryBytes: 536870912 } },
    },
    replicas: { "europe-west4-drams3a": 1 },
  });

  return project("parrilladasC", {
    variables: { managed: false },
    resources: [Postgres, web, postgresVolume],
  });
});
