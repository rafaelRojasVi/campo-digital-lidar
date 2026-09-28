/**
 * The boundary that decides whether this build may offer demo sign-in.
 *
 * The value is Vite's own build mode, not a `VITE_*` variable this repository
 * sets. That distinction is the whole point:
 *
 *  - `import.meta.env.DEV` is `true` only while the module graph is served by
 *    `vite dev` (`npm run dev`, the Vite server on 127.0.0.1:5200 that
 *    scripts/transelec_dev.py starts). Vite replaces it with the literal
 *    `false` in every `vite build` artifact.
 *  - Every deployable artifact of this dashboard is produced by `vite build`
 *    — the Dockerfile's `dashboard-build` stage runs `npm run build`, and
 *    apps/api/app/dashboard_static.py serves only that `dist/` output. There
 *    is therefore no configuration step that could be forgotten, mistyped or
 *    overridden into re-enabling demo sign-in on a hosted deployment; the
 *    demo affordance is not merely hidden there, it is compiled out.
 *
 * Contrast apps/portal/src/runtime/environment.ts, which reads
 * `VITE_CAMPO_ENV` and treats *unset* as `'local'`. That default is correct
 * for what it drives (module copy and iframe URLs) but would fail open here:
 * a hosted build whose environment variable was missing would advertise the
 * seeded identities. This function has no such default to get wrong.
 *
 * This is presentation only, and is never the security control. The server
 * is the authority: `POST /auth/dev-login` is mounted exclusively under
 * `APP_ENV == "development"` (apps/api/app/main.py) and its handler re-checks
 * through `app.dev_auth.assert_dev_auth_allowed`, so a development build
 * pointed at a staging or production API gets a 404 rather than a session.
 */
export function demoSignInAvailable(): boolean {
  return import.meta.env.DEV === true
}
