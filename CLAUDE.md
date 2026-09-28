# Campo Digital Platform — Claude project instructions

This repository is the Campo Digital multi-product platform monorepo. It contains LiDAR / Cubicación, Gestión Predial Forestal / QGIS, and Transelec as separate bounded product contexts.

For all documentation work, follow:

@docs/DOCUMENTATION_POLICY.md

Important project rules:

- Never commit real client LAS/LAZ/ZIP datasets.
- Never infer CRS, coordinate units, sensor precision, or final m³ accuracy without evidence.
- Distinguish confirmed facts from inference and hypothesis.
- Raw geometric volume is not automatically commercial cubicación.
- CloudCompare is a visual inspection/debugging tool; reproducible geometry must live in code/configuration.
- Durable experimental findings, engineering decisions, limitations, failures, and open questions must be documented.

## Campo Digital platform boundaries

This repository now contains three bounded product contexts:

1. LiDAR / Cubicación
2. Gestión Predial Forestal / QGIS
3. Transelec

Do not mix product-specific domain models merely because they coexist in the
same monorepo.

Canonical product boundaries are documented in:

`docs/platform/product-boundaries.md`

## Canonical platform documentation

Before changing shared platform architecture, persistence, source ingestion,
security, environments, or product integration sequencing, read:

- `docs/platform/README.md`
- `docs/platform/system-overview.md`
- `docs/platform/roadmap.md`
- `docs/platform/production-platform-v1.md`
- `docs/platform/source-ingestion.md`
- `docs/platform/client-data-organization.md`
- `docs/platform/security-model.md`
- `docs/platform/environments-and-costs.md`

Treat `docs/research/` as dated supporting evidence, not canonical
architecture. Provider capabilities, regions, limits, and pricing may become
stale and must be re-verified before provisioning.

The stakeholder/project spelling is `Transelec`. The repository product path
currently remains `products/transelect/`; do not rename that path implicitly.

## Transelec workbooks (planillas) — required skill

Before inspecting, importing, validating, publishing or discussing any
Transelec workbook (`PlanillaMaestra*.xlsx`, "planilla", the `Resumen` sheet),
and before changing `products/transelect/src/transelec_ingestion/` layout
recognition, read and follow:

`.claude/skills/transelec-workbook/SKILL.md`

The canonical reading rules are in
`products/transelect/docs/source-contract-v2.md`; the skill is the procedure
and must not duplicate them. Never commit a workbook, never publish or deploy
one without the user's explicit instruction for that workbook, and never put
its business values in commits, PRs or docs.

## External Campo Digital source data

External source material may be available through:

`CAMPO_DIGITAL_SOURCE_ROOT`

Treat that location as read-only unless the user explicitly authorizes a
modification.

Never:

- git-add files from the external source root
- move, rename, or delete external source material
- write generated artifacts into the source root by default
- treat OneDrive as the production application database
- infer that similarly named files belong to the same product context

Canonical source classification is defined in:

`config/source-catalog.yaml`
