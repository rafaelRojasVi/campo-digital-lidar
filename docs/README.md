# Documentation index

[Project README](../README.md) · [English](../README.md#english) · [Español](../README.md#espanol) · [Roadmap](../README.md#roadmap) · [Spanish docs](es/README.md)


This directory contains the engineering and project documentation for the Campo Digital LiDAR timber-measurement PoC.

## Documentation principles

The canonical engineering record is primarily maintained in English.

Spanish documentation under `docs/es/` is intended for Campo Digital and other Spanish-speaking collaborators. It summarizes the same technical truth for that audience rather than mirroring every English document line by line.

Documentation rules are defined in:

- [Documentation policy](DOCUMENTATION_POLICY.md)

Claude project instructions are defined in:

- [`../CLAUDE.md`](../CLAUDE.md)

---

## Core engineering documentation

- [Architecture](architecture.md)
- [Accuracy](accuracy.md)
- [Coordinate systems](coordinate-systems.md)
- [LAS format](las-format.md)
- [Methodology](methodology.md)
- [Sensors](sensors.md)
- [Tooling](tooling.md)

---

## Dataset records

Dataset-specific forensic evidence belongs in:

- [`datasets/`](datasets/)

Current real-data record:

- [`datasets/v01_MG_23jun2026.md`](datasets/v01_MG_23jun2026.md)

Client point-cloud files themselves must never be committed.

---

## Findings

Cross-cutting technical findings belong in:

- [`findings/`](findings/)

Current major finding:

- [Cubicación accuracy: current technical findings](findings/cubicacion_accuracy_problem.md)

---

## Experiments

Reproducible engineering experiments belong in:

- [`experiments/`](experiments/)

Naming convention:

~~~text
EXP-001-description.md
EXP-002-description.md
...
~~~

An experiment should preserve:

- the question;
- hypothesis;
- input;
- method;
- parameters;
- reproduction command;
- result;
- interpretation;
- limitations;
- decision;
- next step.

Template:

- [`templates/experiment.md`](templates/experiment.md)

---

## Engineering decisions

Durable technical decisions belong in:

- [`decisions/`](decisions/)

Naming convention:

~~~text
ADR-001-description.md
ADR-002-description.md
...
~~~

Template:

- [`templates/adr.md`](templates/adr.md)

---

## Engineering journal

Chronological engineering notes belong in:

- [`journal/`](journal/)

The journal records development history but does not replace findings, experiment records, or ADRs.

Template:

- [`templates/journal-entry.md`](templates/journal-entry.md)

---

## Spanish collaboration documentation

Spanish-language project documentation lives in:

- [`es/`](es/)

Main documents:

- [Estado técnico del proyecto](es/estado-proyecto.md)
- [Preguntas abiertas para Campo Digital](es/preguntas-campo-digital.md)
- [Bitácora](es/bitacora/)

---

## Evidence discipline

Documentation should distinguish:

~~~text
FACT
INFERENCE
HYPOTHESIS
DECISION
OPEN QUESTION
LIMITATION
RESULT
~~~

A plausible interpretation must not gradually become a documented fact without new evidence.
