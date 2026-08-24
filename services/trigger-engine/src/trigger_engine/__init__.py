"""Ankur trigger engine: weather panel -> moisture state -> condition -> approved rule.

Stage order, and the module that owns each:

    synthetic     stand-in weather panel while real IMD/ECMWF adapters are unwired
    preprocess    sort, regularize, per-variable imputation, physical caps
    waterbalance  FAO-56 bucket -> root-zone moisture state          (physics, not ML)
    features      causal, shifted predictors -- no value from t or later
    labels        dry-spell onset within a lead window
    splits        leave-one-monsoon-season-out cross-validation
    models        climatology / persistence / raw-ensemble baselines, then calibration
    evaluation    Brier, BSS, reliability, ECE, economic value, block bootstrap
    conditions    moisture state -> ConditionCode                    (deterministic)
    decision      cost-loss threshold + hysteresis                   (deterministic)
    pipeline      wires the above together

The engine never writes to `extracted_rules` and never creates a rule. It reads
only rules a human has approved, via `ankur_domain.policies`. See
`docs/ml-pipeline.md` for the design rationale and `docs/architecture.md` for
where this sits in the system.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
