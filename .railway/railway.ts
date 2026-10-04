import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

// Infrastructure as Code for the production app service. It replaced
// railway.json (Config as Code, removed 2026-10-04), which Railway stops
// reading on 2026-12-01.
//
// Railway does not read this file when it deploys: it changes the service only
// when someone runs `railway config apply` (see
// products/transelect/docs/deployment.md, "Railway build and start"). Run
// `railway config plan` first; it must report no changes.
//
// DECLARE EVERYTHING. Once the service is declared here, an apply treats this
// file as the whole truth for it: a variable, the volume mount or the source
// left out is deleted or detached, not left alone. `preserve()` keeps a
// variable's current value in Railway without writing the value here.
//
// This repository owns the app service and its volume. PostGIS and the
// project's other settings are not declared and stay as they are in Railway.
export const partial = "campo-digital-platform";

export default defineRailway(() => {
  const data = volume("campo-digital-platform-volume", { region: "sfo", sizeMB: 500 });

  const app = service("campo-digital-platform", {
    source: github("rafaelRojasVi/campo-digital-platform"),
    build: { builder: "DOCKERFILE", dockerfilePath: "/Dockerfile" },
    // The image's ENTRYPOINT followed by its own CMD. Railway replaces the
    // ENTRYPOINT with any start command, and the entrypoint is what hands the
    // volume to `campo` and drops root. apps/api/tests/test_railway_config.py
    // fails if this stops matching the Dockerfile.
    start:
      "/usr/local/bin/campo-entrypoint sh -c \"exec uv run --frozen --no-sync uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port ${PORT}\"",
    // Readiness, not liveness: /ready fails without a mounted, writable object
    // store, /health does not.
    healthcheck: "/ready",
    // Migrations are a release step, never part of app startup. Until this
    // file, it was set only in the Railway dashboard.
    preDeploy: ".venv/bin/alembic upgrade head",
    // Uploaded workbooks and Rodales snapshots (CAMPO_OBJECT_STORE_ROOT).
    volumeMounts: { "/data": data },
    env: {
      APP_ENV: preserve(),
      CAMPO_OBJECT_STORE_ROOT: preserve(),
      GOOGLE_CLIENT_ID: preserve(),
      GOOGLE_CLIENT_SECRET: preserve(),
      GOOGLE_REDIRECT_BASE_URL: preserve(),
      GOOGLE_WORKSPACE_DOMAIN: preserve(),
      PLATFORM_BOOTSTRAP_ADMINS: preserve(),
      PLATFORM_TOKEN_ENCRYPTION_KEY: preserve(),
      POSTGRES_DB: preserve(),
      POSTGRES_HOST: preserve(),
      POSTGRES_PASSWORD: preserve(),
      POSTGRES_PORT: preserve(),
      POSTGRES_USER: preserve(),
      RAILWAY_RUN_UID: preserve(),
      TRANSELEC_BOOTSTRAP_ADMIN_EMAIL: preserve(),
    },
  });

  return project("sweet-truth", { resources: [app, data] });
});
