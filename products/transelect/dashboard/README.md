# Transelec dashboard

Private, authenticated dashboard for Campo Digital's Transelec workbooks. It reads the published version through the platform API and separates plan status, detailed exploration, pending work, AEF tracking, data quality and operator actions.

The [functional parity matrix](../docs/audit/2026-09-02-functional-parity-matrix-v1.md) records the original dashboard requirements. The [2026-09-26 usability note](../docs/design/2026-09-26-dashboard-usability-pass.md) records the current interface changes and open business questions.

## Routes

| Route | Audience | Purpose |
|---|---|---|
| `/transelec` | viewer+ | PMF status and work overview |
| `/transelec/explorador` | viewer+ | Search, filters, row detail and CSV export |
| `/transelec/pendientes` | viewer+ | Priority queue and 90-day consultation |
| `/transelec/seguimiento-aef` | viewer+ | AEF tracking by PMF with source rows |
| `/transelec/calidad` | viewer+ | Data-quality findings, reforestation limits and report |
| `/transelec/datos` | operator/admin | Import, versions and (admin only) access management |
| `/transelec/importar`, `/transelec/versiones`, `/transelec/accesos` | role-gated | Direct links to the corresponding Datos panes |

## Data and access

The production dashboard reads authenticated `/api/transelec/*` endpoints. Test fixtures and stubbed API responses are used only by tests. Upload, validation, publication and restore are separate operations; validating a workbook does not publish it. The source workbook stays outside Git. The importer's canonical reading rules are in [Source Contract V2](../docs/source-contract-v2.md).

The CSRF token for mutations is fetched from `GET /api/auth/csrf` and kept in memory. The browser uses the same-origin `/api/*` path and the existing session cookie. The API enforces product roles.

## Local development

From the repository root, use `make transelec-dev` for the complete local stack. For separate processes:

```bash
make platform-local
cd products/transelect/dashboard
npm ci
npm run dev
```

The Vite port is configured by `TRANSELEC_DASHBOARD_PORT` (default `5200`); `/api/*` proxies to `CAMPO_PLATFORM_API_PORT` (default `8000`). Dev sign-in is available only with `APP_ENV=development`.

## Checks

```bash
cd products/transelect/dashboard
npm test
npm run test:e2e
npm run lint
npx tsc -b
npm run build
```

## Brand assets

The header bundles a resized copy of Campo Digital's white logo from its [official website](https://www.campodigital.cl/wp-content/uploads/2019/11/logo-campo-blanco-home-1-02.png). It is served from `src/assets/campo-digital-logo.png`, not hotlinked. Transelec remains readable text in the brand link. The logo from the historical source HTML has not been reused.
