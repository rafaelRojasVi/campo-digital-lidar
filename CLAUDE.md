# Campo Digital LiDAR — Claude project instructions

This repository contains an engineering PoC for LiDAR-based timber measurement and cubicación.

For all documentation work, follow:

@docs/DOCUMENTATION_POLICY.md

Important project rules:

- Never commit real client LAS/LAZ/ZIP datasets.
- Never infer CRS, coordinate units, sensor precision, or final m³ accuracy without evidence.
- Distinguish confirmed facts from inference and hypothesis.
- Raw geometric volume is not automatically commercial cubicación.
- CloudCompare is a visual inspection/debugging tool; reproducible geometry must live in code/configuration.
- Durable experimental findings, engineering decisions, limitations, failures, and open questions must be documented.
