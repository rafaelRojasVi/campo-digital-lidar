# Campo Digital — Company Portal

Company-branded shell that gives one local URL from which the three bounded
products (LiDAR, Forestry, Transelec) can be opened. See
[docs/platform/company-portal-v1.md](../../docs/platform/company-portal-v1.md)
for the architecture decision and the local demo orchestrator
(`make campo-demo`).

This app does not implement product logic. It only knows each module's
display copy and, at runtime, the URL and status a launcher reports through
`public/campo-runtime.json` (generated, git-ignored).

## Development

    npm install
    npm run dev

The portal alone (without `make campo-demo`) shows every module as "Demo no
iniciada" — that is expected; no `campo-runtime.json` has been generated
yet. Run `make campo-demo` from the repository root to start the products
and generate it.

## Checks

    npm run lint
    npm run build
    npm run test
