---
name: transelec-workbook
description: Use when a Transelec planilla / PlanillaMaestra workbook (.xlsx) arrives, when a Transelec import, upload, validate-and-project or publish fails or warns, when the Resumen sheet's headers, columns, auxiliary tables, dates or AEF block change, or before changing transelec_ingestion's layout recognition.
---

# Transelec workbook intake

## Overview

A new planilla is evidence, not an instruction to import. The canonical rules
for reading it live in **one place**:
`products/transelect/docs/source-contract-v2.md` (V1 in `source-contract-v1.md`
still defines identity, status and auxiliary worksheets). This skill is only
the procedure. Never restate the contract's rules here or in code comments;
cite the contract section instead.

## Procedure

1. **Read the contract first.** Read `source-contract-v2.md` end to end,
   especially the sections *Layout recognition*, *Field registry, tiers and
   documented aliases*, *Rows and cells*, *AEF tracking per PMF*, *Severity and
   the import lifecycle* and *Open questions for Campo Digital*.
2. **Keep the file private.** Leave the workbook where the user put it
   (typically `C:\Users\<user>\Downloads\…`, i.e. `/mnt/c/Users/<user>/Downloads/…`
   under WSL), or under `CAMPO_DIGITAL_SOURCE_ROOT` (read-only). Never copy it
   into the repository, never `git add` it, and never paste business values
   (names, predios, roles, AEF text) into chat, commits, PRs or docs.
3. **Inspect structure with the importer's own recognizer:**
   ```bash
   uv run --extra transelec python .claude/skills/transelec-workbook/inspect_workbook.py \
       <workbook.xlsx> --out <scratchpad>/layout-report.json
   ```
   It prints the header row, field → column letter, filled-row counts, column
   decisions, auxiliary regions and issue codes with row counts, and refuses to
   write its JSON report inside the repository.
4. **Compare with the contract**, column by column. Record, for each change:
   | Observation | Contract section to check |
   |---|---|
   | Header row moved, columns inserted/removed | Layout recognition §2, §4 |
   | Header spelled differently | Normalization §3, documented aliases |
   | Blank column or new block beside the table | Blocks §4 (`columna_vacia_intermedia` vs `region_auxiliar_ignorada`) |
   | `Carpeta` columns moved or renamed | §5 (`carpeta_ambigua`) |
   | Same field in two columns | §6 duplicates |
   | Text, dashes or two dates in a date column | Rows and cells (text dates) |
   | AEF / Quién solicita / fechas differ within a PMF | AEF tracking per PMF (`aef_conflicto_pmf`) |
   | Anything the contract does not describe | New OPEN QUESTION — do not guess |
5. **Preserve provenance.** Every finding cites worksheet row numbers
   (`source_row_number`) and column letters. Raw cell text stays raw
   (`source_text_dates`); nothing is filled down, normalized into a new
   meaning, or chosen between conflicting values.
6. **Report before changing anything.** Tell the user: counts (rows, PMF,
   predios), every error / warning / info code with its rows, what is new
   versus the contract, and which items are ambiguous. Label each as FACT,
   INFERENCE, HYPOTHESIS or OPEN QUESTION (see `docs/DOCUMENTATION_POLICY.md`).
   Never invent what AEF or a status means.
7. **Validate privately end to end** only when asked: a disposable
   `*_test` Postgres database (TEMPLATE `template_postgis`), `alembic upgrade
   head`, upload → validate-and-project → review the layout report in
   Datos → Importar. Drop the database afterwards. Do not run
   `make persistence-check` (it resets the shared test container).
8. **Never publish or deploy** a workbook unless the user explicitly says to,
   for that workbook, in this conversation. Warnings require the operator's
   explicit acknowledgement; that is their decision, not yours.
9. **If recognition must change:** update `source-contract-v2.md` first (as a
   DECISION with its evidence), then `transelec_ingestion/resumen_layout.py`,
   its tests (`products/transelect/tests/test_resumen_layout.py`, synthetic
   fixtures only) and, for a real workbook, an opt-in private test gated by an
   environment variable like `TRANSELEC_PRIVATE_WORKBOOK_0909` that asserts
   counts and cell references, never business values. Add the Spanish summary
   for Campo Digital under `products/transelect/docs/es/`.

## Common mistakes

- Reading headers by position or letter: the contract recognizes headers; the
  09-Sept layout shifted every V1 column by five.
- Treating a pivot/summary block to the right of the table as data because
  its labels repeat business headers.
- "Fixing" a two-date cell, a `-`, or an inverted chronology in code.
- Copying the workbook to `tests/`, `data/` or the repo root for convenience.
- Summarizing findings with real names or predio labels.
