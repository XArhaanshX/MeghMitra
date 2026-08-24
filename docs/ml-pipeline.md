# ML pipeline (trigger engine) — design

Status: **first draft built** under `services/trigger-engine/` (synthetic weather,
offline CLI via `make trigger-demo`). Real IMD/ECMWF adapters, spatial join, and
serving into `trigger_events` are not wired. Diagram:
[`ml-pipeline.excalidraw`](./ml-pipeline.excalidraw).
Owner lane: Arhaansh (calibration, preprocessing, water-balance features).
Reader prerequisites: `docs/architecture.md`, `docs/domain-model.md`.

This doc covers the box labelled *"Future (not built yet)"* in `docs/architecture.md` and the
placeholder tables at the bottom of `db/migrations/0001_init.sql`.

---

## 1. Where this plugs into what already exists

The existing repo is the **Rule base** layer of the submission's four-layer design (A. Rule
base, B. GIS/names, C. Trigger, D. Two users). Layers B, C and D are unbuilt.

```
BUILT                                  |  THIS DOC
                                       |
PDF -> loader -> chunker -> extractor  |  weather obs + ensembles
    -> confidence -> validator         |      -> block panel
    -> extracted_rules (Postgres)      |      -> water balance state
    -> /rules, /review-queue API       |      -> p(dry spell)  [the ML]
    -> human approve/reject            |      -> condition_code
                                       |      -> JOIN approved rules  <-- the seam
                                       |      -> advisory + citation
```

The seam is exactly one function that already exists:

```python
# packages/domain/src/ankur_domain/policies.py
def is_advisory_eligible(rule: DACPRule) -> bool:
    return rule.review_status == ReviewStatus.APPROVED and has_valid_citation(rule.citation)
```

The trigger engine's **only** read path into the rule base is this predicate. It never sees
`pending`, `needs_review`, or `rejected` rules, and never sees `confidence`. That is already
the documented design (`docs/decisions.md`, "Confidence blocks the *automated* advisory path")
— the ML layer inherits it rather than re-deciding it.

### Conventions this service must follow

Taken from `AGENTS.md` and `docs/architecture.md`; they are not optional:

- New uv workspace member under `services/`, listed in root `pyproject.toml` `[tool.uv.workspace]`.
- Pydantic shapes go in `packages/schemas/` (`ankur_schemas`), zero business logic, zero I/O.
- Pure decision functions go in `packages/domain/policies.py` style — no I/O, unit-testable
  without Postgres or a NetCDF file.
- Repository access via a `Protocol` in `ankur_domain/repositories.py`, implemented **twice**:
  `ankur_domain/memory.py` and `apps/api/app/db.py`. They must not drift.
- Dependency direction stays one-way. `services/trigger-engine` may import `ankur_domain` and
  `ankur_schemas`; nothing in `packages/` may import it.
- Thin routes, fat services.
- `make test` must keep passing with no live Postgres and no network.

---

## 2. Blocking finding: the rule base is currently empty

**The ML layer has nothing to join to yet.** Measured, not assumed — from a real run of
`uv run python -m document_intelligence.ingest data/raw/HAR16-Sirsa-30-06-2011.pdf`:

```
450 rules extracted from 31 pages
450 flagged needs_review        (100%)
confidence: min 0.35  median 0.35  max 0.67
rules with confidence >= 0.85 (MIN_AUTO_ELIGIBLE_CONFIDENCE):  0
```

Field fill rates across all 450:

| field | filled | | field | filled |
|---|---|---|---|---|
| district | 100.0% | | crop_stage | 0.0% |
| condition | 100.0% | | variety | 0.0% |
| action | 34.0% | | seed_rate | 0.0% |
| crop | 4.4% | | actor | 0.0% |
| block / farming_situation / soil | 0.0% | | | |

### This is a structural ceiling, not a tuning problem

From `services/document-intelligence/src/document_intelligence/confidence.py`:

```
score = 0.35 (base) + 0.20 (header context) + 0.06 * (populated optional fields)
```

To clear `MIN_AUTO_ELIGIBLE_CONFIDENCE = 0.85` a draft needs **≥ 5 populated optional fields**.
The maximum observed anywhere in the 450 is **2** (`crop` + `action`). No amount of threshold
tuning fixes this — the extractor would have to actually start populating `variety`,
`seed_rate`, `crop_stage`, `soil`, and `actor`, which is precisely the multi-line row
reassembly work the README names as the next step.

### And `condition` being "100% populated" is not a quality signal

`extractor.py` falls back to `condition = chunk.text` whenever a row has no header context.
So every row gets a `condition` regardless of whether one exists. Actual sampled values:

```
p8   conf=0.46 | "Condition"
p8   conf=0.46 | "weeks"
p8   conf=0.46 | "situation"
p15  conf=0.61 | "canal/ tubewell"
p16  conf=0.61 | "medium alluvial"
p20  conf=0.35 | "As above    As above    As above"
p27  conf=0.35 | "Before the event   During the event   After the event"
```

And the 4.4% of rows with a `crop` include `crop="CCSHAU, Hisar"`, `crop="Department ,"`,
`crop="water harvesting."` — column bleed, not crops.

**Consequence for planning:** the ML pipeline cannot be demo-validated end-to-end until
extraction produces approved rules. Those two workstreams are parallel, and the ML side must
be built against a **contract**, not against live extractor output. Section 4 defines that
contract so both sides can proceed independently.

---

## 3. Three more findings worth fixing before they reach the demo

### 3.1 The committed fixture cites pages that do not exist

`data/fixtures/sirsa_dacp.json` cites pages **37, 38, 41, 44**.
`data/raw/HAR16-Sirsa-30-06-2011.pdf` has **31 pages**.

All four citations are unverifiable, and rule #1 is seeded `review_status: "approved"` with
`reviewed_by: "fixture-seed"`. This is the exact shape the trigger engine is supposed to trust
absolutely. If it ever leaks past tests into a seed script or demo database, Ankur cites a page
that isn't there — on the one claim the whole product rests on.

### 3.2 Citation page bound (policy tightening, shipped)

`has_valid_citation(..., page_count=)` and `can_approve(..., page_count=)` now reject a page
past the end of the source file when the caller knows `document.page_count`. Omitting
`page_count` preserves the original `page >= 1` behaviour, so existing unbound call sites
(including `data/fixtures/sirsa_dacp.json` pages 37–44, which have no `document_id`) do not
change meaning.

`ReviewService.approve` looks up `page_count` when the rule has a `document_id`.
When the cited page's text is stored, it also requires `source_text` to appear on
that page (`citation_appears_on_page`). Missing snippet or missing page text is
not a failure. Demo seed (`make seed`) now persists the 31 PDF pages as well.

Still open: multi-line table reassembly in extraction, and extractor-assigned
`condition_code`.

### 3.3 The fixture's pytest fixtures are dead

`tests/conftest.py` defines `sirsa_fixture_data` and `sirsa_rules`. Grep across the repo
(excluding `.venv`) finds **no test that requests either**. Meanwhile `README.md` describes the
file as *"Hand-curated Sirsa fixture used by the test suite"* and the fixture's own `_comment`
says it covers *"the invariants the test suite checks."* Neither is currently true. Either wire
them into real assertions or drop them — a fixture that documents coverage it does not provide
is worse than no fixture.

---

## 4. The contract: `condition_code`

**This is the single most important design decision in the ML pipeline, and it is not an ML
decision.** It must be settled before any model code.

`DACPRuleFields.condition` is `str` — free prose. `trigger_events.condition` in
`0001_init.sql` is likewise `TEXT`. The submission claims a *"1:1 map onto a pre-approved
action"*. That map cannot exist while both sides of the join are prose. The ML layer produces
a physical state; the rule base holds a sentence; nothing joins them.

Fix: a closed, versioned vocabulary that both sides target.

```yaml
# packages/schemas/.../condition_taxonomy.yaml  (proposed)
- code: DRY_SPELL_AFTER_SOWING_15_20D
  label_en: "Normal onset followed by 15-20 day dry spell after sowing"
  requires_anchor: sowing_date
  predicate: consecutive_dry_days(since=sowing_date) BETWEEN 15 AND 20
  state_vars: [rain_daily, sowing_date, onset_flag]

- code: DELAYED_ONSET_GT_3W
  label_en: "Delayed onset of monsoon by more than 3 weeks"
  requires_anchor: normal_onset_date
  predicate: onset_date - normal_onset_date > 21 days

- code: UNSEASONAL_RAIN_AT_FLOWERING
  requires_anchor: crop_stage
  predicate: crop_stage == 'Flowering' AND rain_3d_sum > p95_climatology(pentad)
```

Both sides get a new field:

- **Rule side:** `DACPRuleFields.condition_code: str | None = None`, populated by a
  normalization pass (exact match → alias table → constrained-enum fallback). Unmapped stays
  `None`. This follows the documented extension rule in `docs/domain-model.md`: add as
  `str | None`, never required. `condition` stays verbatim — it is what the citation quotes.
- **ML side:** the classifier's output vocabulary *is* this enum. It cannot emit a condition
  the rule base cannot express.

### New metric: condition coverage

```
coverage = approved rules with a non-null condition_code / approved rules
```

Report it from day one. If it is 30%, the product is 30% real, and it is far better to know
that in week 2 than in the finale. Note this metric is currently **undefined** — the
denominator is zero (section 2).

### The join

```sql
SELECT * FROM extracted_rules
WHERE review_status = 'approved'          -- NOT confidence >= 0.85
  AND fields->>'condition_code' = $1
  AND fields->>'district' = $2;
```

Confidence gates entry to the **review queue**. Only `approved` gates **emission**. The
committed fixture illustrates why these are different axes: rule #2 has `confidence 0.88`
(above threshold) but is still `pending`; rule #4 has `confidence 0.79` and is `rejected`.
Neither may fire. This is already `is_advisory_eligible`'s behaviour — do not reimplement it.

---

## 5. The ML pipeline

### 5.1 It is not one model

Three components, three eval protocols, three audit records. Do not build end-to-end.

| # | Component | Type | Learned? | Primary metric |
|---|---|---|---|---|
| M1 | Ensemble → block dry-spell probability | probabilistic classifier | yes | Brier Skill Score vs climatology |
| M2 | Root-zone water balance | physical bucket model | parameters only | RMSE vs ERA5-Land soil moisture |
| M3 | Cost–loss decision policy | deterministic | no | Richardson value V(α) |

M2 and M3 belong in `ankur_domain`-style pure functions (no I/O, unit-testable). Only M1 needs
a model artifact. This split is what keeps the audit trail legible and what lets `make test`
stay database-free and network-free.

### 5.2 Stages

```
S0  contracts        condition_taxonomy.yaml, block registry, crop/variety aliases, licence tags
S1  ingest           IMD gridded rain, ECMWF ensembles, ERA5-Land, soil AWC, ENSO/IOD/MJO
S2  spatial          grid -> block (area-weighted); emits the panel key (block_id, date)
S3  preprocess       sort/dedup, asfreq('D'), per-variable impute + outlier policy, flags
S4  water balance    daily bucket -> soil moisture state, deficit, dry-run length      [M2]
S5  features         causal shifted lags/rollings, anomalies, ensemble stats, exogenous
S6  labels           dry-spell onset within [t+1, t+L], L in {7,14,21,30}
S7  splits           leave-one-monsoon-season-out CV; 2025 held out
S8  models           baselines B0..B2 -> M1 -> recalibration                           [M1]
S9  eval             BSS, reliability, ECE, sharpness, block-bootstrap CI
S10 decision         cost-loss threshold p* = alpha, hysteresis                        [M3]
S11 condition map    state -> condition_code -> approved-rule join -> ABSTAIN default
S12 serve + audit    nightly precompute -> trigger_events; full provenance
S13 monitor          drift, calibration decay, alert rate, graceful degradation
```

### 5.3 S4 — water balance (the physical prior that makes small data work)

```
S_t   = clamp(S_{t-1} + P_eff,t - ET_c,t, 0, AWC)
P_eff = P - runoff                    (SCS curve number, or a simple threshold)
ET_c  = Kc(crop, stage) * ET0
ET0   = Hargreaves (needs only Tmin/Tmax/lat) or FAO-56 Penman-Monteith if RH + wind available
```

Emits `sm_frac = S_t/AWC`, `cum_deficit`, `days_since_rainy_day`, `consecutive_dry_days`,
`sowing_moisture_ok`. Parameters (`AWC`, `Kc`, curve number) fitted on **train years only**,
per soil class; validated against ERA5-Land.

This is a simulator, not ML, and saying so plainly is a strength — it is the physics that lets
a 12-feature logistic regression work on ~40 seasons of data.

### 5.4 S6 — label definition (freeze and version this)

```
dry_day      := daily rainfall < 2.5 mm        (IMD rainy-day threshold)
dry_spell_5d := >= 5 consecutive dry_days
y(t, L)      = 1 if a dry_spell_5d begins within [t+1, t+L]
```

The flagship Sirsa rule needs a **15–20 day** spell, which is a different and far rarer label
than 5 days. Train both; report both base rates.

**Sowing anchor:** the flagship condition is anchored on sowing date. Make it an explicit input
(farmer-declared, or block-modal from an agri calendar), never inferred — an inferred anchor
makes the trigger unfalsifiable.

### 5.5 S8 — model ladder (deliberately short)

| ID | Model | Purpose |
|---|---|---|
| B0 | Climatology: dry-spell base rate by pentad × block | the BSS reference denominator |
| B1 | Persistence | shows why the load-forecasting result does not transfer |
| B2 | **Raw uncalibrated ensemble fraction** | the "ECMWF/IMD already does this" bar |
| M1a | Quantile mapping / EMOS → logistic | classic, interpretable |
| M1b | Logistic regression, ~12 features | primary candidate |
| M1c | LightGBM, monotonic constraints, depth ≤ 4 | only if M1b is clearly beaten in CV |
| M1d | Isotonic / Platt recalibration | final calibration polish |

**Stop there.** No LSTM, no transformer — and this is a positioning strength, not a shortcut.
"We benchmarked 17 architectures across six families in prior work and found complexity has
diminishing returns; here we chose the smallest model that calibrates" is a much stronger
answer than a PatchTST overfitting ~120 events.

**B2 is the bar that matters.** If calibration does not beat the raw ensemble fraction, there
is no ML contribution — say so and shift emphasis to extraction and the decision layer.

### 5.6 S10 — decision layer (no learning)

With `α = C/L` (cost of acting over loss avoided): act when `p > α`, so `p* = α`.

```
V(α) = (E_climatology - E_forecast) / (E_climatology - E_perfect)
```

Report **V across the full range of α** — the value curve, not one number. That is the honest
way to say "worth it for a smallholder with no borewell, marginal for an irrigated farm."

**Hysteresis is mandatory.** The submission commits to "SMS must not double-fire." Require `p`
to hold across the threshold for two consecutive cycles before the advisory state changes.

### 5.7 S11 — the ABSTAIN invariant

"Silent if the plan is silent" must be enforced in the **ML layer**, not just the UI.

ABSTAIN is an explicit output class and the **default**. Emit only when all four hold:
calibrated `p` in range, a `condition_code` matched, a rule joined with
`is_advisory_eligible(rule) == True`, and its citation re-verified against the source page
(section 3.2). Any missing link → ABSTAIN, logged with the reason.

This deserves the same treatment the existing invariants got — a pure function in
`ankur_domain.policies`, plus a unit test, plus a DB `CHECK`. Mirror how
`approved_rules_require_citation` is enforced redundantly in both Python and Postgres.

---

## 6. What transfers from the load-forecasting paper — and what must not

The submission commits to importing *"only"* the preprocessing template. Correct instinct.
But three parts of that pipeline are actively wrong for rainfall.

### Transfers cleanly

| Step | Retarget |
|---|---|
| Chronological sort + dedup | key becomes `(block_id, date)` |
| Regular frequency, explicit NaN at gaps | `asfreq('D')` per block, Jun 1 – Sep 30 + 30d spin-up |
| **Causal shifted lags and rollings** (all built off `t-1`) | the single most valuable habit — leakage killer |
| Scaler fitted train-partition-only | fit **inside each CV fold**, not once globally |
| Strict chronological split | becomes leave-one-monsoon-season-out |
| Fixed seed, deterministic ops | keep |

### Does not transfer

**1. 4σ winsorization on rainfall — remove it.** Load is roughly Gaussian around a diurnal
cycle. Daily rainfall is zero-inflated and heavy-tailed, and the extreme *is* the signal
(burst, revival). Clipping at μ+4σ deletes the events you exist to detect. Use a physical
plausibility cap only, plus `log1p` for feature use. Keep 4σ for temperature and soil moisture.

**2. Forward-fill on rainfall — remove it.** Forward-filling a missing rain day carries
yesterday's 40 mm into today: a fabricated rain event. Zero-filling fabricates a dry day, which
biases the target directly. Policy must be per-variable:

| Variable | Missing policy |
|---|---|
| Rainfall | spatial infill from neighbouring cells (IDW), else mask + `is_imputed` flag |
| Soil moisture (state var, has inertia) | ffill ≤ 2 days then interpolate — the paper's rule is right *here* |
| Temperature | linear interpolate ≤ 3 days |
| Ensemble fields | never impute; a missing cycle = ABSTAIN that day |

Any target window containing an imputed observation day is **dropped from labels**. Features
may keep the imputed value with its flag; labels may not.

**3. "Persistence beats complexity" — does not carry over.** That came from 15-minute load with
extreme lag-1 autocorrelation. Daily rainfall at 7–30 day lead has near-zero autocorrelation
past ~2 days. Persistence will lose badly, and that is expected. The reference baseline is
**climatology**, which is what BSS is defined against.

**4. MAE / RMSE / MAPE — wrong metric family.** You are emitting a probability. Use Brier, BSS,
reliability + ECE, ROC-AUC / PR-AUC, and the value curve.

**5. `W=192` sliding windows, 45 flattened features, 3D tensors — wrong data shape.** Load was
long-and-narrow (245k rows, one series). This is short-and-wide: ~122 monsoon days × N blocks ×
~40 years, heavily spatially correlated. Panel framing, not sequence-tensor framing.

**6. Feature selection placement.** The paper's Algorithm 1 selects features at steps 23–27,
i.e. **before** the split at step 27. That is a leak. Select inside the fold.

---

## 7. Sample size — the biggest honest risk

For Sirsa alone: ~7 blocks × 122 monsoon days × 40 years ≈ 34,000 block-days. That number is
misleading. Blocks within one district are near-perfectly spatially correlated (~1–2 independent
spatial samples, not 7) and dry spells are autocorrelated (~2–4 independent events per season).
Effective positives ≈ **40 seasons × ~3 ≈ 120**.

Consequences, as design decisions rather than surprises:

1. **Train wide, demo narrow.** Pool across Haryana and comparable agro-climatic zones; demo on
   Sirsa. Include block-static covariates so a pooled model can specialise.
2. **Keep the model small,** with monotonic constraints (p must rise with ensemble dry-fraction
   and with cumulative deficit). Cheap regularisation *and* defensible to an agronomist.
3. **Never report a bare point estimate.** Block-bootstrap 95% CI on BSS, always.
4. **Report effective sample size explicitly.** A judge who asks and gets a straight answer
   trusts the rest.
5. **The 2025 hold-out is one sample.** Use it as *narrative* in the demo; use
   leave-one-season-out CV as *evidence* in the metrics table.

### Data risk that gates everything: reforecasts

Calibrating an ensemble needs forecast–observation pairs across many years. ECMWF open-data
live ENS gives roughly two. ECMWF **re-forecasts** and the **S2S database** exist precisely for
this and cover the 7–30 day subseasonal window the PS asks about. **Verify open-access terms
and the retrieval path in week 1** — if reforecasts are not obtainable, M1 as specified is not
trainable, and the fallback is a climatology-conditioned model with no ensemble input. Decide
before writing model code.

---

## 8. Build order

**Phase 0 — unblock the join (not ML work, but gates all of it)**
1. Multi-line table row reassembly in `extractor.py` (already the README's next step)
2. `condition_code` taxonomy + normalization pass; measure condition coverage
3. Fix the fixture's out-of-range citations; add the page upper bound to `has_valid_citation`
4. First batch of genuinely approved Sirsa rules through the review UI

**Phase 1 — contracts**
5. Block registry + 2011-district → current-block crosswalk (the reorganisation test)
6. Verify ECMWF reforecast / S2S access — go/no-go for M1

**Phase 2 — data spine**
7. S1–S3 ingest, block aggregation, preprocessing with the corrected per-variable policies
8. S4 water balance, validated against ERA5-Land

**Phase 3 — model**
9. S6–S7 labels + leave-one-season-out CV harness
10. B0/B1/B2 baselines **first** — you need the bar before the model
11. M1b, then M1c only if CV justifies it, then M1d

**Phase 4 — decision + serve**
12. M3 cost–loss + hysteresis
13. S11 condition mapping, approved-rule join, ABSTAIN as a policy function + test + CHECK
14. S12 nightly precompute into `trigger_events`, audit log, fallback JSON

**Phase 5 — replay demo**
15. Monsoon 2025 Sirsa replay, ~10 blocks, against the naive "it rained so sow" contrast

Phases 0–1 are the critical path. Phases 2–3 can run in parallel with Phase 0 **only** because
section 4 defines the contract; without it they will not meet.

---

## 9. Proposed layout

```
services/trigger-engine/src/trigger_engine/
    ingest/        imd_rain.py  ecmwf_ens.py  era5_land.py  indices.py
    spatial/       grid_to_block.py  crosswalk_2011.py
    preprocess/    clean.py  impute.py  outliers.py       # per-variable policies live here
    waterbalance/  bucket.py  et0.py  params.py           # pure functions       [M2]
    features/      build.py  registry.py                  # each declares its causal shift
    labels/        dryspell.py
    splits/        season_cv.py
    models/        baselines.py  calibrate.py  m1_logistic.py  m1_lgbm.py   [M1]
    eval/          brier.py  reliability.py  value.py  leadtime.py  bootstrap.py
    conditions/    map_state_to_code.py

packages/schemas/.../ condition.py        # ConditionCode enum, TriggerEvent, ForecastSnapshot
packages/domain/.../  policies.py         # + can_emit_advisory()  [M3, ABSTAIN]
                      repositories.py     # + WeatherRepository, TriggerRepository Protocols
                      memory.py           # + in-memory impls (keep make test DB-free)
apps/api/app/db.py                        # + Postgres impls (must not drift from memory.py)
tests/unit/           test_abstain.py  test_costloss.py  test_waterbalance.py
                      test_causal_shift.py  test_no_fit_outside_fold.py
```

The last two tests are the leakage guards; the first is the product's integrity claim expressed
as CI. Write them early.

---

## 10. Open questions

1. **Reforecast access** — who resolves it, by when? Gates the entire ML plane.
2. **Condition coverage** — if only a handful of Sirsa rules end up with machine predicates, do
   we narrow the demo to those, or widen to more districts to find more mappable rules?
3. **Sowing anchor** — farmer-declared (needs the SMS loop) or block-modal from an agri
   calendar? Determines whether the flagship condition is evaluable at all.
4. **Block vs district granularity** — DACP rules are district-level; the forecast is
   block-level. The submission's "soil-based sub-district split" is an assumption with no
   validation data. Claiming district resolution with block-level *timing* is defensible;
   claiming block resolution may not be.
5. **Dry-spell length** — train on 5-day (more events, better calibration) and map up to the
   15–20 day DACP condition, or train directly on 15–20 day (matches the rule, ~10× rarer)?
   Recommendation: both, report both base rates.
6. **Region to widen training to** beyond Haryana?
7. **Does `condition_code` belong in `DACPRuleFields` or in a separate join table?** Putting it
   in `fields` (JSONB) needs no migration and follows `docs/domain-model.md`'s extension rule,
   but a re-normalization pass then rewrites rule rows. A side table keeps extracted rules
   immutable — which better matches "re-running extraction never mutates a persisted rule."
   Domain owner's call.
