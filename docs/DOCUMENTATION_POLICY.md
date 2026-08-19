# Documentation policy

## Purpose

Documentation in this repository is part of the engineering evidence.

The goal is to preserve:

- what was observed;
- how it was observed;
- what is inferred;
- what remains unknown;
- why engineering decisions were made;
- which experiments succeeded or failed;
- and what Campo Digital still needs to clarify.

Documentation must never convert uncertainty into false certainty.

---

## Canonical language strategy

### English

Use English for canonical engineering documentation:

- source-code documentation;
- architecture;
- implementation methodology;
- dataset forensics;
- experiments;
- engineering decisions;
- algorithms;
- reproducibility instructions;
- technical findings.

These documents are the authoritative technical record.

### Spanish

Use Spanish for collaboration with Campo Digital and Chilean stakeholders:

- project status;
- explanations of findings;
- questions for Campo Digital;
- meeting notes;
- operational/domain notes;
- stakeholder-facing summaries;
- project diary when useful for collaborators.

Spanish documents do not need to mirror every English technical document line by line.

Do not maintain two independent technical sources of truth.

---

## Evidence labels

Durable technical claims should be mentally classified using the following categories.

### FACT

Directly established by:

- source data;
- code;
- reproducible command output;
- confirmed client information;
- or an authoritative source.

Example:

> All 4,109,685 two-record GPS timestamp groups in the current LAS are ordered Return 1 -> Return 2.

### INFERENCE

Interpretation strongly supported by evidence but not directly proven.

Example:

> The export preserves a structured relationship between GPS timestamps and return numbers.

### HYPOTHESIS

A proposition that still requires an experiment or external confirmation.

Example:

> Return 1 and Return 2 may correspond to first and second physical echoes from the same emitted pulse.

### DECISION

An engineering choice and its rationale.

Example:

> Geometry uses observed point bounds rather than stale LAS-header bounds.

### OPEN QUESTION

Information still required from Campo Digital, the dataset, hardware documentation, or further experimentation.

Example:

> Which sensor produced `v01_MG_23jun2026.las`?

### LIMITATION

Something the current method or dataset cannot establish.

Example:

> A visible log end does not uniquely determine the hidden log length.

### RESULT

The output of a defined, reproducible experiment.

Results must identify enough context to reproduce or interpret them.

---

## Documentation destinations

### `docs/findings/`

Durable cross-cutting technical findings.

Use when the result changes our understanding of the problem.

### `docs/datasets/`

Dataset-specific forensic records.

Use for:

- provenance;
- hashes;
- point count;
- dimensions;
- bounds;
- CRS;
- acquisition metadata;
- dataset-specific anomalies.

### `docs/experiments/`

One record per meaningful experiment.

Use names such as:

`EXP-001-las-forensics.md`

`EXP-002-return-pairing.md`

`EXP-003-timber-stack-roi.md`

### `docs/decisions/`

Architecture/engineering decision records.

Use names such as:

`ADR-001-use-observed-las-bounds.md`

### `docs/journal/`

Concise chronological engineering log.

This records what happened during development without replacing formal experiment or decision records.

### `docs/es/`

Spanish collaboration/stakeholder documentation.

Important files include:

- `estado-proyecto.md`
- `preguntas-campo-digital.md`
- `bitacora/`

---

## Experiment documentation

A meaningful experiment should record:

- question;
- hypothesis;
- input;
- method;
- parameters;
- reproducibility command;
- result;
- interpretation;
- limitations;
- decision;
- next step.

A failed experiment is still worth documenting if it changes future engineering decisions.

Do not rewrite a failed experiment as if it succeeded.

---

## Decision records

Create an ADR when an engineering choice is expected to matter later.

Each ADR should contain:

- status;
- context;
- decision;
- rationale;
- consequences.

Do not use ADRs for trivial implementation details.

---

## Spanish stakeholder documentation

Spanish documentation should prioritize clarity over implementation detail.

Explain:

- what we discovered;
- why it matters;
- what problem remains;
- what decision was made;
- what Campo Digital needs to answer;
- what happens next.

Do not blindly translate large English technical files.

Summarize the technical truth for the intended audience.

---

## Client-data rules

Never commit:

- client LAS;
- LAZ;
- ZIP archives;
- private coordinates when disclosure is inappropriate;
- client-identifying raw outputs;
- private reference measurements without explicit approval.

`data/raw/` and `data/interim/` are local working areas.

Before committing a derived report from client data, review whether it reveals sensitive information.

---

## Accuracy and units

Never silently assume:

- coordinate units are metres;
- a LAS numeric scale is sensor accuracy;
- a sensor specification equals final measurement accuracy;
- a geometric volume equals commercial cubicación;
- LiDAR360 or Pix4D output is perfect ground truth.

Use `source units` until linear units are confirmed.

Do not make m³ accuracy claims without:

- confirmed units;
- same-object reference measurement;
- same ROI;
- defined cubicación target;
- reproducible comparison.

---

## Documentation workflow

At the end of a meaningful engineering session:

1. inspect the code diff and test results;
2. identify durable FACTS, RESULTS, LIMITATIONS, DECISIONS, and OPEN QUESTIONS;
3. update the relevant canonical English technical document;
4. create/update an experiment record if an experiment occurred;
5. create/update an ADR if a durable decision occurred;
6. update Spanish stakeholder documentation if the information matters to Campo Digital;
7. append a concise journal entry;
8. review documentation diff before committing;
9. run `python scripts/update_doc_nav.py` when documentation files or navigation targets are added, removed, moved, or renamed;
10. run `python scripts/check_doc_links.py` and resolve broken local documentation links.

Documentation automation must not automatically commit changes.

---

## Translation rule

Translation must preserve technical meaning.

Do not translate identifiers such as:

- LAS;
- LAZ;
- LiDAR;
- SLAM;
- ROI;
- PDAL;
- CloudCompare;
- FastAPI.

Useful bilingual terminology may be written as:

- point cloud (nube de puntos);
- ground truth (medición de referencia);
- return (retorno);
- registration (registro/alineamiento);
- bounding box (caja envolvente);
- source units (unidades de origen).

Avoid awkward literal translations when the English technical term is standard.

---

## Claude documentation behavior

When asked to document the current work:

- inspect repository state first;
- read relevant existing documentation;
- avoid duplicating established facts;
- preserve numeric precision when it matters;
- distinguish evidence from inference;
- update only files relevant to the current work;
- never invent missing client information;
- never rewrite source-code behavior from assumptions;
- show the proposed documentation diff for review;
- do not commit unless explicitly instructed.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../README.md) · [Docs index](README.md) · [Findings](findings/cubicacion_accuracy_problem.md) · [Experiments](experiments) · [Decisions](decisions) · [Spanish docs](es/README.md) · [Estado técnico](es/estado-proyecto.md) · [Preguntas Campo Digital](es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
