
# Ankur — Complete Architecture Guide

SIH 2026 · SIH26086 · Ministry of Earth Sciences · Corpus: India-wide (646 documents, 30 states/UTs) · Flagship demo scope: Haryana → Sirsa

This document explains the whole system, starting from plain English and going down to
each stack in detail. Read Part 1 even if you only care about one layer — the rest only
makes sense once you know what the product refuses to do.

**Contents**

- [Part 1 — In plain English](#part-1--in-plain-english)
- [Part 2 — The whole system at a glance](#part-2--the-whole-system-at-a-glance)
- [Part 3 — Document ingestion pipeline](#part-3--document-ingestion-pipeline)
- [Part 4 — Domain layer (the rules that never bend)](#part-4--domain-layer-the-rules-that-never-bend)
- [Part 5 — ML pipeline / trigger engine](#part-5--ml-pipeline--trigger-engine)
- [Part 6 — Backend API](#part-6--backend-api)
- [Part 7 — Database](#part-7--database)
- [Part 8 — Frontend dashboard](#part-8--frontend-dashboard)
- [Part 9 — Infrastructure, testing, CI](#part-9--infrastructure-testing-ci)
- [Part 10 — End-to-end walkthrough](#part-10--end-to-end-walkthrough)
- [Part 11 — Current status and honest gaps](#part-11--current-status-and-honest-gaps)

---

## Part 1 — In plain English

### The problem

A farmer in Sirsa waits for the first monsoon rain. It comes, so he sows. Then the rain
stops for twenty days. The seedlings die. He buys seed a second time and sows again.

That is the loss Ankur exists to prevent. In one Maharashtra soybean season, roughly 20%
of 43 lakh hectares needed re-sowing.

### The thing almost everyone misses

**The government already wrote down what he should have done instead.**

ICAR-CRIDA published about 650 District Agriculture Contingency Plans (DACPs). The Sirsa
plan, dated 30 June 2011, already says: if there is a normal onset followed by a 15–20 day
dry spell after sowing, re-sow pearl millet with variety HHB-67 Improved, and the Block
Agriculture Officer should stage the seed.

That advice is sitting in a scanned PDF. It gets opened at one pre-season meeting a year,
and consulted after a drought is already declared. Nobody has made those plans
machine-readable and connected them to a live weather forecast.

### What Ankur is

Ankur is a **contingency-plan trigger engine**. Three sentences:

1. It reads DACP PDFs and turns the tables inside into structured, citable rules.
2. It watches the weather and works out which of the plan's own named conditions is
   currently happening.
3. When a condition matches an approved rule, it shows that rule — with the PDF page
   number it came from.

### What Ankur is NOT — and this is the important part

| Not this             | Because                                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A weather forecaster | IMD already launched an AI block-level onset model in May 2026 covering 3,196 blocks. Building a worse copy would be pointless. Ankur**consumes** forecasts and never declares onset. |
| An advice generator  | It never invents a crop, variety, seed rate, or action. Every word of advice is retrieved from a government document.                                                                       |
| A chatbot over PDFs  | Extraction is deterministic table parsing against a known schema, not "chat with the document."                                                                                             |

The one-line rule the entire codebase is built around:

> **Ankur retrieves pre-approved government contingency actions. It does not generate
> agricultural advice. If the plan is silent, Ankur is silent.**

### The analogy

Think of a **pharmacist**, not a doctor.

A doctor diagnoses and invents a treatment. A pharmacist reads the prescription, checks it
is genuine and signed, and hands over exactly what it says — no more. If there is no
prescription, the pharmacist hands over nothing.

Ankur is the pharmacist. ICAR-CRIDA is the doctor who wrote the prescription in 2011. IMD
supplies the thermometer.

### Why "silence" is a feature

Most days in a monsoon are unremarkable. The system's normal, correct, most common output
is **ABSTAIN** — say nothing.

This matters because the cost of being wrong is asymmetric. A farmer who acts on bad advice
buys a seed bag he did not need, or loses a season he could have saved. So the system is
built to need four separate things to line up before it opens its mouth (Part 4).

---

## Part 2 — The whole system at a glance

### Two pipelines that never talk to each other

```
        ┌──────────────────────────────────────┐
        │  PIPELINE A: Document intelligence   │
        │  "What does the plan say?"           │
        │                                      │
        │  DACP PDF ──► structured rules       │
        │              ──► human review        │
        │              ──► APPROVED rules      │
        └──────────────────┬───────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │    Postgres     │  ◄── the ONLY meeting point
                  │ extracted_rules │
                  └────────┬────────┘
                           │  reads APPROVED rules only
                           ▼
        ┌──────────────────────────────────────┐
        │  PIPELINE B: Trigger engine (ML)     │
        │  "What is the weather doing?"        │
        │                                      │
        │  rainfall ──► soil moisture          │
        │           ──► condition detected     │
        │           ──► match rule ──► advise  │
        └──────────────────────────────────────┘
```

**The extractor never sees weather. The trigger engine never creates a rule.** They are
sibling packages that do not import each other — that isolation is the code-level
expression of the product rule.

### Full stack diagram

```
┌───────────────────────────────────────────────────────────────────────┐
│  apps/app        Next.js 16 dashboard                                 │
│                  /rules  /review  /evaluate  /audit                   │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ HTTP only (no shared code)
┌───────────────────────────────▼───────────────────────────────────────┐
│  apps/api        FastAPI :8000                                        │
│                  thin routes → domain services                        │
│                  IngestionService + AdvisoryEmissionService           │
└──────┬──────────────────────────────────────────────┬─────────────────┘
       │                                              │
┌──────▼───────────────────────┐   ┌──────────────────▼─────────────────┐
│ services/                    │   │ services/                          │
│   document-intelligence      │   │   trigger-engine                   │
│   PDF → rules                │   │   weather → condition → advisory   │
└──────┬───────────────────────┘   └──────────────────┬─────────────────┘
       │                                              │
       └──────────────┬───────────────────────────────┘
                      │  both import (never the reverse)
       ┌──────────────▼──────────────┐
       │ packages/domain             │  invariants, ports, services
       │   ankur_domain              │  PURE — no I/O
       └──────────────┬──────────────┘
       ┌──────────────▼──────────────┐
       │ packages/schemas            │  Pydantic models
       │   ankur_schemas             │  no logic, no I/O
       └─────────────────────────────┘

       ┌─────────────────────────────┐
       │ packages/geo                │  state/district identity, resolve_region(),
       │   ankur_geo                 │  season + condition-threshold params — leaf,
       │                             │  no internal imports (used today by
       │                             │  document-intelligence's state resolution)
       └─────────────────────────────┘

       ┌─────────────────────────────┐
       │ Postgres 16 + PostGIS       │
       └─────────────────────────────┘
```

### Dependency rule (one-way, never violated)

```
schemas ◄── domain ◄── document-intelligence ──┐
                   ◄── trigger-engine ─────────┼──► apps/api ──► apps/app
                                               ┘
geo (leaf, no internal deps) ◄── document-intelligence   (state resolution during ingestion)
```

`packages/` never imports `apps/` or `services/`. `apps/api` is the only place allowed to
import both services — which is why `IngestionService` and `AdvisoryEmissionService` live
there rather than inside the services themselves.

### Directory map

```
ankur/
├── apps/
│   ├── api/              FastAPI service
│   │   └── app/
│   │       ├── routes/   health, documents, rules, review, advisories
│   │       ├── db.py     Postgres repositories (asyncpg, raw SQL)
│   │       ├── deps.py   dependency injection
│   │       ├── ingestion.py   PDF pipeline → DB
│   │       └── advisory.py    trigger engine → DB
│   └── app/              Next.js dashboard (separate pnpm project)
│
├── packages/
│   ├── schemas/          ankur_schemas — Pydantic shapes
│   ├── domain/           ankur_domain — invariants + ports + services
│   └── geo/              ankur_geo — state/district identity, resolve_region(),
│                           season/threshold params (India-wide, corpus-derived)
│
├── services/
│   ├── document-intelligence/   PDF → structured rules
│   └── trigger-engine/          weather → moisture → condition → advisory
│
├── db/migrations/        0001_init.sql, 0002_wire_trigger_emission.sql
├── data/
│   ├── raw/              source DACP PDFs
│   ├── processed/        ingest output (gitignored)
│   └── fixtures/         hand-curated test/demo JSON
├── docs/                 architecture, api, database, domain-model, ml-pipeline
├── scripts/              dev.ps1, migrate.py
└── tests/                unit/ + integration/  (96 tests, no DB needed)
```

---

## Part 3 — Document ingestion pipeline

**Location:** `services/document-intelligence/`
**Job:** DACP PDF → structured, citable rule drafts
**Key property:** deterministic. Not an LLM, not RAG, not fuzzy matching.

### Flow

```
data/raw/HAR16-Sirsa-30-06-2011.pdf
        │
        ▼
┌───────────────────────────────────────────────────────┐
│ loader.py                                             │
│  pdftotext -layout  (pypdf as fallback)               │
│  → page-numbered text, column alignment preserved     │
│  → OCR Protocol if a page has no text layer           │
└───────────────────┬───────────────────────────────────┘
                    ▼
┌───────────────────────────────────────────────────────┐
│ chunker.py                                            │
│  classify each LINE:  heading | table_row | paragraph │
│  never merges across a page boundary                  │
└───────────────────┬───────────────────────────────────┘
                    ▼
┌───────────────────────────────────────────────────────┐
│ extractor.py                                          │
│  1. find a real header row  (must contain a           │
│     "condition" column + ≥1 other known column)       │
│  2. map cells → fields by column position             │
│  3. missing cell → null   (NEVER guessed)             │
│  header state RESETS at every page break              │
└───────────────────┬───────────────────────────────────┘
                    ▼
┌───────────────────────────────────────────────────────┐
│ confidence.py    score_draft()                        │
│  0.35 base + 0.20 header context + 0.06 × each        │
│  populated optional field − 0.15 short condition      │
│  weighted and inspectable — NOT a learned model       │
└───────────────────┬───────────────────────────────────┘
                    ▼
┌───────────────────────────────────────────────────────┐
│ validator.py → ankur_domain.policies                  │
│  assigns  pending | needs_review                      │
│  NEVER assigns approved                               │
└───────────────────┬───────────────────────────────────┘
                    ▼
              extracted_rules (Postgres)
                    │
                    ▼
              Human reviewer → approve / reject
```

### Why `pdftotext` and not `pypdf`

Discovered, not assumed. `pypdf`'s text decoder mangles this specific PDF's embedded font
encoding — it inserts a spurious `H` in place of most spaces. `pdftotext -layout` decodes
it correctly *and* preserves the column alignment the table parser depends on. `pypdf` is
kept as a portability fallback and still supplies page count.

That `H`-for-space quirk shows up again later, in citation verification (Part 4).

### Why header-gated extraction

An early run produced ~500 spurious "rules" from unrelated tables in the district profile
(land use, irrigation sources). Requiring a recognised contingency-table header before any
row is treated as a candidate removed that entire class of noise, rather than trying to
filter it afterwards.

### The `DACPRule` shape

```json
{
  "fields": {
    "state": "Haryana",
    "district": "Sirsa",
    "block": null,
    "farming_situation": null,
    "crop": "Pearl millet",
    "soil": null,
    "crop_stage": "After sowing",
    "condition": "Normal onset followed by 15-20 day dry spell after sowing",
    "condition_code": "dry_spell_after_sowing",
    "action": "Re-sow",
    "variety": "HHB-67 Improved",
    "seed_rate": null,
    "actor": "Block Agriculture Officer"
  },
  "citation": {
    "document": "HAR16-Sirsa-30-06-2011.pdf",
    "page": 37,
    "source_text": "Delay by 15-20 days after normal onset: Re-sow Pearl millet HHB-67"
  },
  "confidence": 0.94,
  "review_status": "approved"
}
```

Every field except `state`, `district`, and `condition` is nullable. **Nullable over guessed,
always.**

### `condition` vs `condition_code` — the join contract

This distinction is the hinge of the whole system.

| Field              | What it is                        | Used for                                       |
| ------------------ | --------------------------------- | ---------------------------------------------- |
| `condition`      | Free prose, verbatim from the PDF | The citation. What a human reads and verifies. |
| `condition_code` | Closed enum (`ConditionCode`)   | The join. What the trigger engine matches on.  |

The weather side produces a *physical state*. The rule side holds a *sentence*. Prose and
physics do not join. `condition_code` is the machine-checkable projection of the prose, and
it is the only field the trigger engine looks at.

`None` means normalization has not run yet. `UNMAPPED` means it ran and failed — and
`UNMAPPED` can never fire an advisory. Those two are deliberately different: one is a
backlog item, the other is a coverage fact.

### Known limitation (real, not hypothetical)

Running the extractor on the committed Sirsa PDF today:

```
450 rules extracted from 31 pages
450 flagged needs_review        (100%)
confidence: min 0.35, median 0.35, max 0.67
rules clearing the 0.85 auto-eligible bar: 0
```

This is a **structural ceiling, not a tuning problem.** Clearing 0.85 requires ≥5 populated
optional fields; the maximum observed anywhere is 2. The DACP tables wrap each row across
multiple physical lines, and the extractor reads one line at a time.

That is the intended failure mode — ambiguous rows are quarantined for a human, never
auto-approved — but it means **multi-line row reassembly is the top-priority next task.**

---

## Part 4 — Domain layer (the rules that never bend)

**Location:** `packages/domain/src/ankur_domain/`
**Job:** hold the safety invariants as pure functions — no I/O, no database, no PDF.

They are pure precisely so they can be unit-tested without infrastructure, and so both the
extractor and the API call the same code instead of re-implementing the rule.

### The four invariants

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. NO CITATION → NO APPROVED RULE                               │
│    has_valid_citation() + can_approve()                         │
│    Enforced AGAIN as a Postgres CHECK constraint.               │
│    Belt and braces — a Python bug cannot bypass the DB.         │
├─────────────────────────────────────────────────────────────────┤
│ 2. EXTRACTION NEVER SELF-APPROVES                               │
│    initial_review_status() returns only pending|needs_review.   │
│    Only a human hitting POST /rules/{id}/approve can approve.   │
├─────────────────────────────────────────────────────────────────┤
│ 3. NULL OVER GUESSED                                            │
│    Missing source data stays null. Never inferred, never        │
│    backfilled from general agricultural knowledge.              │
├─────────────────────────────────────────────────────────────────┤
│ 4. ABSTAIN IS THE DEFAULT                                       │
│    can_emit_advisory() — silence unless everything lines up.    │
└─────────────────────────────────────────────────────────────────┘
```

### Confidence vs approval — two different axes

A common misreading. They gate different things:

```
confidence  ──gates──►  entry to the REVIEW QUEUE
approval    ──gates──►  EMISSION to a farmer
```

`can_approve()` deliberately does **not** check confidence. A human reviewer may approve a
low-confidence rule after reading the source page — that is a legitimate override. What is
blocked is the *automated* path ever treating a low-confidence extraction as trustworthy.

### The emission gate

`can_emit_advisory()` — four conditions, all required:

```
        detected condition exists?
                  │ no ──► ABSTAIN
                  ▼ yes
        code is emittable (not UNMAPPED)?
                  │ no ──► ABSTAIN
                  ▼ yes
        matched rule is APPROVED with a valid citation?
                  │ no ──► ABSTAIN
                  ▼ yes
        rule's condition_code == detected code?
                  │ no ──► ABSTAIN
                  ▼ yes
        ✅ EMIT — with page citation attached
```

**The probability never enters this decision.** A high probability cannot conjure a rule.
The probability only shapes *which action* is recommended, after permission to speak has
already been granted.

### Citation verification (two layers)

```
Layer 1  has_valid_citation(citation, page_count=N)
         → document named?  page ≥ 1?  page ≤ N?

Layer 2  citation_appears_on_page(citation, page_text)
         → does the quoted source_text actually occur on that page?
```

Layer 1's page bound exists because the committed fixture cited pages 37–44 of a **31-page**
PDF. `page >= 1` alone accepts all of them.

Layer 2 matches **ordered significant tokens** (length ≥ 4, stopwords dropped) rather than
raw substrings — because of that `H`-for-space font quirk and because DACP cells wrap across
lines. If either the snippet or the page text is missing, it returns "cannot verify" rather
than inventing a rejection.

### Repository ports

Defined as `Protocol`s, so two implementations satisfy the same contract structurally with
no inheritance:

| Implementation          | Where             | Used by          |
| ----------------------- | ----------------- | ---------------- |
| `ankur_domain.memory` | in-memory dicts   | tests, local dev |
| `apps/api/app/db.py`  | asyncpg + raw SQL | production       |

These two **must stay behaviourally identical** — that is what lets the whole test suite run
without a database.

---

## Part 5 — ML pipeline / trigger engine

**Location:** `services/trigger-engine/`
**Job:** rainfall + temperature + ensemble forecast → moisture state → condition → advisory

### First, the crucial framing

This is **not** a rainfall forecasting model. The output is:

```
(block, date, lead) ──► p(dry spell)      calibrated probability
                   ──► condition_code     enum, or None
                   ──► action             SOW | WAIT | RE_SOW | ABSTAIN
```

Everything is designed backwards from that contract.

### Three separable components — never one end-to-end model

| #            | Component                         | Type                     | Learned?        | Metric               |
| ------------ | --------------------------------- | ------------------------ | --------------- | -------------------- |
| **M1** | Ensemble → dry-spell probability | probabilistic classifier | **yes**   | Brier Skill Score    |
| **M2** | Root-zone water balance           | physical simulator       | parameters only | RMSE vs ERA5-Land    |
| **M3** | Cost–loss decision policy        | deterministic rule       | **no**    | Economic value V(α) |

Keeping them separate is what makes the audit trail legible and each piece testable in
isolation. Only M1 is machine learning.

### Full pipeline flow

```
  raw observations (block, date, rain, tmin, tmax, ens_dry_fraction)
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ preprocess.py                                            │
│  • sort + dedup on (block, date)                         │
│  • asfreq('D') — gaps become NaN ROWS, not missing rows  │
│  • PER-VARIABLE imputation (see below)                   │
│  • physical plausibility cap (NOT 4σ winsorization)      │
│  • trim to JJAS + 30-day spin-up                         │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ waterbalance.py       [M2 — physics, no ML]              │
│  ET0 = Hargreaves-Samani (needs only Tmin/Tmax)          │
│  S_t = clip(S_{t-1} + P_eff − Kc·ET0, 0, AWC)            │
│  → soil_moisture_fraction, consecutive_dry_days          │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ features.py     12 CAUSAL features                       │
│  every feature declares its min_shift_days               │
│  a test deletes the future and re-derives to prove it    │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ labels.py       y(t,L) = dry spell BEGINS in (t, t+L]    │
│  labels MAY see the future; features MAY NOT             │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ splits.py       leave-one-MONSOON-SEASON-out CV          │
│  season is the only near-independent axis                │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ models.py       B0 → B1 → B2 → M1a → M1c → M1d           │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ evaluation.py   Brier, BSS, reliability, ECE, AUC,       │
│                 economic value, block-bootstrap CI       │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│ conditions.py   MoistureState → ConditionCode | None     │
│ decision.py     p + cost-loss α → action + hysteresis    │
└──────────────────────────────────────────────────────────┘
```

### 5.1 Preprocessing — three rules INVERTED from the load-forecasting paper

The preprocessing template came from prior short-term load forecasting work. Three of its
steps carry over. Three had to be **inverted**, because rainfall is not electricity demand.

#### ✅ Carried over

| Step                                     | Why it still applies                                                                                                               |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Chronological sort + dedup               | Ordering is ordering.                                                                                                              |
| Regular frequency, explicit NaN at gaps  | If a gap stays absent, a rolling 7-day window silently spans 9 calendar days and every lag is wrong — an error that never raises. |
| All lags/rollings built off`t-1`       | The single most valuable habit. Leakage killer.                                                                                    |
| Scaler fitted on training partition only | Refitted**inside each CV fold** here.                                                                                        |
| Strict chronological splitting           | Becomes leave-one-season-out.                                                                                                      |
| Fixed seed (42)                          | Reproducibility.                                                                                                                   |

#### ❌ Inverted — and why

**1. 4σ winsorization → physical cap only**

Electricity load is roughly Gaussian around a diurnal cycle, so clipping at μ ± 4σ removes
sensor artifacts. Daily rainfall is **zero-inflated and heavy-tailed**: μ + 4σ falls
*inside* the range of genuine monsoon bursts. Clipping there deletes exactly the revival
events the system exists to detect.

Now: reject only physically impossible values (> 1000 mm/day, or negative). A 250 mm burst
passes through untouched.

**2. Blanket forward-fill → per-variable policy**

Forward-filling a missing rain day carries yesterday's 40 mm into today — **inventing a rain
event.** Zero-filling invents a dry day, which biases the dry-spell target in the direction
that makes the model look better than it is.

| Variable           | Policy                         | Reason                                                        |
| ------------------ | ------------------------------ | ------------------------------------------------------------- |
| **Rainfall** | none — stays NaN, row flagged | Any imputation fabricates weather                             |
| Soil moisture      | ffill ≤ 2 days                | Real physical inertia — the paper's rule is right*here*    |
| Temperature        | interpolate ≤ 3 days          | Smooth, autocorrelated, only feeds ET0                        |
| Ensemble           | none                           | A missing forecast cycle is a reason to abstain, not to guess |

Any target window touching an unobserved rainfall day is **dropped from labels**.

**3. "Persistence beats complexity" → does not transfer**

In the load benchmark, persistence won outright (1.63% MAPE, best of 17 models) because
15-minute demand is overwhelmingly autocorrelated at lag 1. Daily rainfall autocorrelation
decays to near zero within ~2 days. Persistence is kept on the ladder specifically to
*measure* that difference rather than assume it — and it duly loses.

**4. Metric family** — MAPE, MAE, RMSE are all absent. They measure distance between two
numbers. This system outputs a *probability* against a 0/1 outcome. "MAPE of a probability"
is not a quantity.

**5. Feature selection placement** — the paper's Algorithm 1 selects features at steps 23–27,
*before* the split at step 27. That is a leak. Not reproduced.

### 5.2 Water balance (M2) — physics, not ML

```
P_eff = P × (1 − runoff_fraction)          effective rainfall
ET0   = 0.0023 × Ra × (Tmean + 17.8) × √(Tmax − Tmin)     Hargreaves-Samani
ET_c  = Kc × ET0                           crop demand
S_t   = clip(S_{t−1} + P_eff − ET_c, 0, AWC)
```

**Why a single-layer bucket:** FAO-56's single-Kc form is the variant that runs on the
inputs we actually have per block. Dual-Kc needs wet-surface fraction and per-stage rooting
depth we do not have. A Richards-equation solver needs soil hydraulics that do not exist at
3,196-block resolution for India. A wrong complicated model is worse than an honest simple
one.

**Why Hargreaves-Samani, not Penman-Monteith:** PM is FAO-56's primary method but needs
humidity, wind, and radiation. Block-scale grids reliably carry only Tmin/Tmax. Hargreaves
is FAO-56's own documented fallback for exactly this case. The `√(Tmax − Tmin)` term is a
cloudiness proxy — which is why it degrades least during the monsoon, when the diurnal
range genuinely does collapse on rainy days.

**Why this matters for the ML:** handing the model a *soil moisture deficit* instead of
thirty raw lagged rainfall columns removes most of what it would otherwise have to learn
from data it does not have. The physics is what lets a 12-feature model work on ~40 seasons.

**Performance:** the bucket is a recursion (clamped, so not a cumsum). Rather than loop over
rows, it pivots to a (days × blocks) matrix and loops over **days** — ~150 vectorized steps
regardless of block count.

### 5.3 Features — 12, all causal

```
Water balance   sm_frac_lag1, sm_frac_delta_7d, dry_run_lag1
Ensemble        ens_dry_fraction          ◄── strongest single input
Rainfall        rain_sum_7d, rain_sum_30d, dry_days_15d
Anomaly         rain_anomaly_15d          (vs train-only pentad climatology)
Calendar        day_of_season_sin, day_of_season_cos
Teleconnection  oni_lag30, mjo_amplitude_lag10
```

**Why 12 and not 45.** The load paper used 45 features against 245,000 rows. Here there are
roughly **120 effective independent events**. 45 features would be fitting noise with high
confidence.

**Retargeting from the load feature set:**

| Load pipeline                    | Ankur                            |
| -------------------------------- | -------------------------------- |
| lags 1–672 (15-min steps)       | rain lags 1–30 (days)           |
| Fourier P=96 (day), P=672 (week) | Fourier P=122 (season) only      |
| cyclical hour, day-of-week       | day-of-season sin/cos            |
| —                               | soil moisture from FAO-56 bucket |
| —                               | ensemble dry-fraction            |
| —                               | ENSO / MJO teleconnections       |

Diurnal and weekly harmonics are dropped outright — there is no hour or day-of-week
structure in daily block rainfall.

**Causality is enforced structurally, not by convention.** Each feature declares
`min_shift_days`. A test rebuilds the whole matrix from a panel with the future deleted and
requires the surviving rows to match. A leaked feature produces a beautiful validation score
and a worthless forecast, and it is nearly undetectable by eye.

**Monotonic constraints** — physics we already know, encoded:

```
ens_dry_fraction  +1     more members forecasting dry cannot LOWER risk
dry_run_lag1      +1
dry_days_15d      +1
sm_frac_lag1      −1     a wetter profile cannot RAISE risk
rain_sum_7d       −1
```

These do three jobs at once: hard regularization on a small sample, an explicable partial
dependence plot for an agronomist, and monotone threshold behaviour so a farmer seeing a
higher probability never gets a *less* cautious recommendation.

### 5.4 Labels

```
dry_day   := daily rainfall < 2.5 mm      ← IMD's own rainy-day definition
dry_spell := ≥ 5 consecutive dry_days
y(t, L)   =  1 if a dry_spell BEGINS within (t, t+L]
```

**2.5 mm is not a tunable** — it is IMD's operational definition. Using anything else would
mean our "dry spell" and the DACP's "dry spell" are different events, and the citation would
be misleading even when extraction was perfect.

**"BEGINS", not "occurs"** — if we labelled "a spell is in progress", a spell already
underway would label the next 30 days positive, and a model could score well by reporting
the present instead of forecasting.

**Why 5 days when the Sirsa rule says 15–20:** a 15–20 day spell is roughly an order of
magnitude rarer. At ~40 seasons there are too few positives to calibrate on. We train on the
frequent event and map upward at the condition layer — and the ELR model (below) makes that
mapping *coherent* rather than a fudge.

### 5.5 Splits — leave-one-monsoon-season-out

The season is the only axis along which samples are close to independent:

- consecutive days share most of their target window
- blocks within one district see the same synoptic systems

A random split would put day 12 in training and day 13 in test — that is not validation,
it is asking the model to interpolate a curve it has already seen.

**Everything is refitted inside each fold**: climatology, scaler, feature selection,
water-balance parameters. Climatological normals feel like a fixed property of a place,
which is exactly why computing them once over the whole record is such a tempting leak.

The final season (2025) is held out entirely, outside the rotation.

### 5.6 The model ladder

| ID            | Model                                        | Purpose                                                                      |
| ------------- | -------------------------------------------- | ---------------------------------------------------------------------------- |
| **B0**  | Climatology (base rate by seasonal phase)    | The BSS denominator                                                          |
| **B1**  | Persistence                                  | Proves the load-paper result does not transfer                               |
| **B2**  | **Raw uncalibrated ensemble**          | **The bar that decides if this project has an ML contribution at all** |
| **M1a** | Extended Logistic Regression (Wilks 2009)    | Primary calibrator                                                           |
| **M1c** | HistGradientBoosting + monotonic constraints | Only if it beats M1a in CV                                                   |
| **M1d** | Isotonic recalibration                       | Final calibration polish                                                     |

**B2 is the one that matters.** If calibration cannot beat simply counting ensemble members,
the honest report is that the ensemble is already well calibrated here and Ankur's value
lies entirely in extraction and the decision layer. That result must be *reportable*, so the
baseline is a first-class model, not a footnote.

**Why Extended Logistic Regression is primary.** Standard logistic regression fits one model
per threshold, which multiplies parameters and lets curves *cross* — producing the
incoherent claim that a 15-day spell is likelier than a 5-day one. Wilks (2009) made the
threshold itself a predictor:

```
logit P(L ≥ g | x) = x'β − γ·√g
```

Here the threshold axis is **spell length**, which solves a real problem in this project:
one fit yields P(≥5d) *and* P(≥15d), guaranteed monotone in g. It is also the method the
literature still benchmarks against for subseasonal Indian-monsoon calibration, and it
specifically outperforms separate fits when the training record is **short** — our regime.

**Why the ladder stops at gradient boosting.** Prior work benchmarked 17 architectures across
6 families under one pipeline and found a clean inverse relationship between complexity and
accuracy (PatchTST: 376× the training time for twice the error). That was on 245,000 rows.
Here there are ~120 independent events. Adding an LSTM would repeat an experiment whose
answer we already have, with a hundredth of the data.

### 5.7 Evaluation

| Metric                         | Answers                                           |
| ------------------------------ | ------------------------------------------------- |
| Brier score                    | Proper scoring rule — cannot be gamed by hedging |
| **Brier Skill Score**    | Does it beat climatology?*(headline)*           |
| Reliability / ECE              | When we say 30%, does it happen 30% of the time?  |
| Sharpness                      | Does it dare to leave the base rate?              |
| ROC-AUC                        | Discrimination, independent of calibration        |
| **Economic value V(α)** | What is it worth to a farmer?                     |
| Block-bootstrap CI             | Honest error bars                                 |

**Murphy decomposition** — `BS = reliability − resolution + uncertainty`. Worth splitting
because the two controllable terms need different fixes: poor reliability is a calibration
problem (isotonic helps), poor resolution is a signal problem (only better predictors help).

**Block bootstrap resamples whole seasons, not rows.** Resampling rows would treat ~10,000
correlated observations as 10,000 independent ones and produce an interval several times too
narrow — the statistical form of quoting "34,000 block-days" as the sample size.

**Effective sample size is reported deliberately pessimistically** — positives ÷ lead_days ÷
n_blocks. Its entire job is to stop anyone over-claiming.

### 5.8 Decision layer (M3) — no learning

A probability is not a decision. "60% chance of a dry spell" does not tell a farmer with
four acres and no borewell whether to sow on Tuesday.

**Cost–loss model.** With `α = C/L` (cost of acting ÷ loss avoided), the expected-cost-
minimising rule is **act when p > α**, so `p* = α`.

This puts the threshold in the *farmer's* hands, not ours:

```
smallholder, no borewell  → small α → warned EARLY
irrigated farm            → large α → warned RARELY
```

Same probability, two different *correct* answers. That is why economic value is reported as
a **curve across α**, never a single number.

**Hysteresis is mandatory.** A probability jittering around α produces WAIT, SOW, WAIT on
consecutive days — each individually defensible, the sequence worthless, and given the SMS
commitment, expensive. A new action must persist for 2 cycles before it takes effect. The
system is slower to *change its mind* than to speak for the first time.

**Seed demand (objective O4):**

```
quintals = hectares × p(trigger) × seed_rate × safety_factor ÷ 100
```

`seed_rate` must come from the matched rule. It is currently `null` in every fixture rule, so
a missing rate **raises** rather than silently producing zero quintals — which a BAO could
read as "stage nothing."

### 5.9 Conditions — physics → government vocabulary

```
ConditionCode:
  DELAYED_ONSET            onset > 21 days late
  DRY_SPELL_AFTER_SOWING   ← flagship (the re-sow case)
  MID_SEASON_DRY_SPELL     break during vegetative growth
  TERMINAL_DROUGHT         deficit at grain fill (DOY ≥ 250)
  UNSEASONAL_RAIN          3-day rain > 3× pentad normal
  UNMAPPED                 normalization failed — NEVER emittable
```

**Priority order, most specific first** — after-sowing leads because it is the only one
carrying a re-sow decision and a named variety. Mid-season trails as the catch-all.

**The key agronomic distinction:** a dry spell over a *wet* profile is a meteorological
event, not an agricultural one. The crop is fine. So the drought conditions require
`consecutive_dry_days ≥ 5` **AND** `soil_moisture_fraction < 0.35`. Firing on rainfall alone
would cost a farmer a seed bag for nothing.

**The sowing anchor is never inferred.** Without an explicit `days_since_sowing`, the
flagship condition cannot fire regardless of how extreme the weather is. An inferred sowing
date would make the condition unfalsifiable — and this is the condition that tells a farmer
to spend money on seed twice.

### 5.10 Synthetic data — read this before quoting any number

`synthetic.py` generates the weather used by tests and `make trigger-demo`. It exists
because `make test` must run with no network, and every real input (IMD gridded, ECMWF,
ERA5-Land) is network-fetched.

It is a Richardson-type stochastic weather generator: a two-state Markov chain for wet/dry
occurrence (which is what creates realistic dry *spells*) plus a gamma distribution for
intensity (right-skewed, unlike a normal). The synthetic ensemble is deliberately
**over-confident**, reproducing the under-dispersion of real ensembles so calibration has
something genuine to correct.

> **Any skill score from this data measures whether the CODE works, not whether the METHOD
> works.** Every output path prints this caveat.

### 5.11 Actual measured output

```
$ make trigger-demo

effective sample size: {rows: 27065, positives: 14422, seasons: 31,
                        blocks: 7, approx_independent_events: 147}

  M1c_gradient_boosted    L=14d  BS=0.2202  BSS=+0.034  ECE=0.032  AUC=0.683  BSS95%=[+0.008,+0.065]
  M1a_extended_logistic   L=14d  BS=0.2209  BSS=+0.031  ECE=0.038  AUC=0.678  BSS95%=[+0.008,+0.051]
  B0_climatology          L=14d  BS=0.2279  BSS=+0.000  ECE=0.036  AUC=0.649
  B1_persistence          L=14d  BS=0.2476  BSS=−0.087  ECE=0.070  AUC=0.472
  B2_raw_ensemble         L=14d  BS=0.3159  BSS=−0.386  ECE=0.263  AUC=0.583

economic value: (0.20,+0.07) (0.35,+0.13) (0.50,+0.23) (0.65,+0.06) (0.80,−0.01)

total wall time: 7.3s
```

Reading this: calibration beats climatology (CI excludes zero); the raw ensemble is badly
miscalibrated (ECE 0.26) exactly as the generator intended; persistence loses, confirming the
load result does not transfer. At **7-day** lead the simpler ELR actually beats the boosted
model — which is the ladder doing its job.

---

## Part 6 — Backend API

**Location:** `apps/api/`
**Stack:** FastAPI · asyncpg · raw SQL (no ORM)

### Endpoints

```
GET  /health                              liveness (stays 200 even if DB is down)

GET  /documents                           list ingested PDFs
GET  /documents/{id}
GET  /documents/{id}/pages                page text
GET  /documents/{id}/pages/{page}         ← powers citation verification
POST /documents/ingest                    run the extraction pipeline

GET  /rules                               list (filter by review_status)
GET  /rules/{id}
GET  /rules/{id}/citation                 "why did Ankur say this?"

GET  /review-queue                        rules needing human eyes
POST /rules/{id}/approve                  ← the ONLY path to approved
POST /rules/{id}/reject

POST /advisories                          evaluate weather → advisory or ABSTAIN
GET  /advisories                          emissions (non-silent only)
GET  /trigger-events                      ALL evaluations, including ABSTAIN
```

### Layering: thin routes, fat services

```
route handler          translates domain exceptions → HTTP status codes
      │                ONLY that. No business logic.
      ▼
domain service         business rules meet persistence
      │
      ▼
repository (Protocol)  in-memory (tests) | asyncpg (production)
```

### The two orchestration services

Both live in `apps/api` — not in the services themselves — because this package is the only
one allowed to import both siblings.

```
IngestionService          PDF → document_intelligence → Postgres
AdvisoryEmissionService   moisture + forecast → trigger_engine → Postgres
```

### `POST /advisories` flow

```
request { district, moisture, forecast, cost_loss_ratio, crop_already_sown }
        │
        ▼
rules.list_advisory_eligible(district)    ← APPROVED + cited only
        │                                   pending/rejected never reach the engine
        ▼
detect_condition(moisture)                ← physics only, no model
        │
        ▼
emit_advisory(...)  →  can_emit_advisory()  ← the 4-way gate
        │
        ▼
citation_appears_on_page(rule, page_text)   ← final verification
        │  fails ──► force ABSTAIN
        ▼
write TriggerEvent   (ALWAYS — even on ABSTAIN)
write Advisory       (only if NOT abstain)
        │
        ▼
response { action, detected_condition, abstain_reasons, rule, citation, ... }
```

**Every evaluation is logged, including silence.** An audit log that only recorded the times
the system spoke would hide the more common — and more important — silences.

### Design choices

- **Raw SQL over an ORM** — the schema is small and still settling. `db.py` is meant to be
  read top to bottom.
- **API boots even if Postgres is down** — DB routes return 503, `/health` stays 200. Keeps
  process supervision simple and the demo resilient.
- **JSONB for `fields`/`citation`** — DACP documents vary district to district.
  Column-per-field would force a migration for every new district's quirks.

---

## Part 7 — Database

**Postgres 16 + PostGIS**

```
┌─ EXTRACTION SIDE ──────────────────────────────────────┐
│ documents           filename, district, sha256, pages  │
│ document_pages      text per page, extraction_method   │
│ extracted_rules     fields JSONB, citation JSONB,      │
│                     confidence, review_status          │
│                     CHECK approved ⇒ citation exists   │
│ rule_citations      indexed provenance lookup          │
│ extraction_runs     one row per ingest invocation      │
│ review_queue        reserved worklist                  │
└────────────────────────────────────────────────────────┘

┌─ TRIGGER SIDE ─────────────────────────────────────────┐
│ blocks              geom MultiPolygon 4326  (reserved) │
│ weather_observations                        (reserved) │
│ forecast_snapshots                          (reserved) │
│ soil_data                                   (reserved) │
│ trigger_events      block_key, condition, reasons,     │
│                     payload — EVERY evaluation         │
│ advisories          action, reason, rule_id — emissions│
│ audit_logs                                             │
└────────────────────────────────────────────────────────┘
```

### The database-level invariant

```sql
CONSTRAINT approved_rules_require_citation
    CHECK (review_status <> 'approved' OR (citation ->> 'document') IS NOT NULL)
```

Intentionally redundant with the Python check. A bug that bypasses the domain layer entirely
still cannot write an approved rule without a citation.

### Migrations

| File                               | What                                                                                                            |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `0001_init.sql`                  | Core tables + trigger-side placeholders                                                                         |
| `0002_wire_trigger_emission.sql` | Promoted`block_key`/`reasons`/`action`/`reason` from JSONB into real columns, backfilling existing rows |

Tracked in a `schema_migrations` table; `make migrate` is idempotent.

---

## Part 8 — Frontend dashboard

**Location:** `apps/app/` · Next.js 16 · TypeScript · Tailwind · shadcn/ui · TanStack Query · Zustand

Separate pnpm project. Talks to the API over **HTTP only** — it shares no code with the
Python workspace.

### Pages

```
/            Dashboard home — counts, health
/rules       Browse extracted rules (filter, search, paginate)
/rules/[id]  Detail: fields, citation, review metadata, confidence notes
/review      Review queue — approve / reject
/evaluate    Fire a test evaluation against the trigger engine
/audit       Trigger events + advisories (the audit trail)
```

### Structure

```
src/
├── app/(dashboard)/     route group — pages + colocated _components/
├── api/                 one module + one hooks module per resource
│                        rules.ts / rules-hooks.ts, advisories.ts, ...
├── components/
│   ├── ui/              shadcn primitives
│   └── motion/          transition wrappers
├── hooks/  stores/  schemas/  lib/  utils/
```

Pattern: `<resource>.ts` holds fetch functions and types; `<resource>-hooks.ts` wraps them in
TanStack Query hooks with a query-key factory. Components never call `fetch` directly.

---

## Part 9 — Infrastructure, testing, CI

### Local development

```bash
cp .env.example .env
uv sync                 # one venv for the entire Python workspace

make docker-up          # Postgres/PostGIS, waits for healthy
make migrate            # idempotent
make dev                # FastAPI :8000
make web                # Next.js :3000  (separate terminal)

make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf
make trigger-demo       # ML verification sweep (synthetic weather)
make test  /  make lint  /  make format
make help               # lists every target
```

### The uv workspace

`apps/api`, `packages/schemas`, `packages/domain`, `services/document-intelligence`, and
`services/trigger-engine` are **one uv workspace** — one venv, one lockfile, editable
cross-package imports with no publishing step. `apps/app` is managed separately by pnpm.

### Testing — 96 tests, no database required

```
tests/unit/
  test_citations.py         invariant 1 — citation gating
  test_confidence.py        invariant 2 — extraction never self-approves
  test_extraction.py        table parsing
  test_validation.py        draft → rule
  test_rule_service.py      service layer
  test_trigger_engine.py    42 tests — the ML pipeline

tests/integration/
  test_ingestion.py         real pipeline against the real committed PDF
  test_rules_api.py         FastAPI + in-memory repos
  test_advisories_api.py    full evaluate → persist flow
  test_seed_demo.py         demo seed integrity
```

Integration tests use `app.dependency_overrides` with in-memory repositories — **no live
Postgres**. That is a hard constraint: do not add a live-DB requirement to the default run.

**Tests that are product claims, not ordinary tests:**

| Test                                                        | Guards against                                       |
| ----------------------------------------------------------- | ---------------------------------------------------- |
| `test_features_are_causal`                                | Leakage — rebuilds features with the future deleted |
| `test_climatology_is_fitted_in_fold`                      | The subtlest leak (normals over the whole record)    |
| `test_every_condition_code_has_a_predicate`               | Vocabulary advertising coverage that cannot fire     |
| `test_abstain_is_the_default`                             | Speaking without permission                          |
| `test_monotonic_constraints_are_respected`                | Physically nonsensical model behaviour               |
| `test_extended_logistic_is_coherent_across_spell_lengths` | P(≥15d) > P(≥5d), which is impossible              |

### CI/CD

`.github/workflows/api-image.yml` and `web-image.yml` build container images on push to
`main`, path-filtered so unrelated changes do not trigger rebuilds.

---

## Part 10 — End-to-end walkthrough

Following one real advisory from PDF to farmer.

```
① INGEST
   make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf
   → loader → chunker → extractor → confidence → validator
   → 450 rule drafts, all needs_review
                    │
                    ▼
② HUMAN REVIEW
   Reviewer opens /review, reads page 37 of the source PDF,
   confirms the row, clicks Approve.
   → can_approve() checks the citation
   → Postgres CHECK enforces it again
   → review_status = approved
                    │
                    ▼
③ WEATHER ARRIVES
   Rainfall + temperature for Sirsa's blocks
   → preprocess → water balance
   → soil_moisture_fraction = 0.20,  consecutive_dry_days = 10
                    │
                    ▼
④ FORECAST
   ML pipeline → p(dry spell in next 14 days) = 0.80
   (calibrated, with model_version stamped)
                    │
                    ▼
⑤ CONDITION DETECTION            ← physics only, NO model
   days_since_sowing = 10  (explicitly provided, never inferred)
   dry_run ≥ 5  AND  soil < 0.35
   → DRY_SPELL_AFTER_SOWING
                    │
                    ▼
⑥ RULE MATCH
   list_advisory_eligible("Sirsa")   → approved + cited only
   find rule where condition_code == DRY_SPELL_AFTER_SOWING
                    │
                    ▼
⑦ THE GATE — can_emit_advisory()
   condition detected?          ✓
   code emittable?              ✓
   rule approved + cited?       ✓
   codes match?                 ✓
   source_text on page 37?      ✓
                    │
                    ▼
⑧ DECISION           p=0.80 > α=0.35, crop already sown
   → RE_SOW
                    │
                    ▼
⑨ PERSIST
   TriggerEvent  (always)
   Advisory      (because not ABSTAIN)
                    │
                    ▼
⑩ OUTPUT
   "Re-sow Pearl millet with HHB-67 Improved."
   Source: HAR16-Sirsa-30-06-2011.pdf, page 37
   Every word retrieved. Nothing generated.
```

### The same walk when the plan is silent

```
Weather is extreme, but no approved rule matches the detected condition
        │
        ▼
can_emit_advisory() → (False, ["no matching approved rule"])
        │
        ▼
TriggerEvent written with the reason.   Advisory: NONE.
        │
        ▼
Output: ABSTAIN — the system says nothing.
```

That path is the product working correctly.

---

## Part 11 — Current status and honest gaps

### Built and working

| Layer                 | Status                                                                                     |
| --------------------- | ------------------------------------------------------------------------------------------ |
| Document intelligence | ✅ Deterministic PDF → rules, confidence, review routing                                  |
| Domain invariants     | ✅ 4 invariants, pure functions, DB-enforced too                                           |
| ML pipeline           | ✅ Full preprocessing → water balance → features → labels → CV → ladder → evaluation |
| Decision layer        | ✅ Cost-loss, hysteresis, seed demand                                                      |
| Backend API           | ✅ 15 endpoints incl. advisory evaluation                                                  |
| Database              | ✅ 2 migrations, invariant as CHECK                                                        |
| Frontend              | ✅ 6 pages, review + evaluate + audit                                                      |
| Tests                 | ✅ 96 passing, no DB, no network                                                           |

### The gaps — stated plainly

**1. The rule base is effectively empty.** 450/450 rules sit at `needs_review`, max
confidence 0.67 against a 0.85 bar. It is a structural ceiling: clearing 0.85 needs ≥5
populated optional fields, and the maximum observed is 2. **Multi-line table row reassembly
is the highest-priority task in the project** — the trigger engine has almost nothing real
to join to until it lands.

**2. Weather data is synthetic.** No IMD or ECMWF adapters are wired. Every skill number
currently produced verifies the code, not the method.

**3. Reforecast access is unresolved.** Calibrating an ensemble needs many years of
forecast–observation pairs. ECMWF opened its full real-time catalogue under CC-BY-4.0 on
1 Oct 2025, but **reforecast/hindcast access still needs confirming** — and if it is not
obtainable, M1 as designed is not trainable and the fallback is a climatology-conditioned
model with no ensemble input.

**4. Condition coverage is unmeasured.** The fraction of approved rules carrying a usable
`condition_code` is currently undefined because the denominator is zero. If it turns out to
be 30%, the product is 30% real — and it is far better to learn that early.

**5. Sowing anchor has no source.** The flagship condition needs `days_since_sowing` from
somewhere real — farmer-declared via SMS, or block-modal from an agri calendar. Until then
it cannot fire in production.

**6. Block vs district granularity.** DACP rules are district-level; forecasts are
block-level. The "soil-based sub-district split" is an assumption with no validation data.
District resolution with block-level *timing* is defensible; block resolution may not be.

### Priority order

```
1. Multi-line row reassembly       → unblocks everything downstream
2. condition_code normalization    → measure coverage
3. Confirm ECMWF reforecast access → go/no-go for the ML plane
4. Real IMD ingest adapter         → replaces synthetic weather
5. Sowing anchor source            → makes the flagship condition live
6. Block registry + GIS crosswalk  → real block boundaries
```

---

## Appendix — Quick reference

### Key files

```
packages/domain/.../policies.py     THE invariants — read first
packages/schemas/.../condition.py   ConditionCode — the join contract
packages/schemas/.../rule.py        DACPRule — the central object

services/document-intelligence/.../extractor.py     table parsing
services/document-intelligence/.../confidence.py    scoring

services/trigger-engine/.../config.py        every constant + its justification
services/trigger-engine/.../preprocess.py    the 3 inverted rules
services/trigger-engine/.../waterbalance.py  FAO-56 physics
services/trigger-engine/.../models.py        the ladder + why it stops
services/trigger-engine/.../conditions.py    physics → vocabulary
services/trigger-engine/.../decision.py      cost-loss + hysteresis

apps/api/app/advisory.py            wires engine to persistence
db/migrations/0001_init.sql         schema + the CHECK constraint
```

### Numbers that are definitions, not choices

| Value   | Source                                              |
| ------- | --------------------------------------------------- |
| 2.5 mm  | IMD rainy-day threshold                             |
| 0.0023  | Hargreaves-Samani coefficient                       |
| p* = α | Cost-loss optimum (decision theory)                 |
| 0.85    | `MIN_AUTO_ELIGIBLE_CONFIDENCE` — project choice  |
| 21 days | "more than 3 weeks" — the Sirsa plan's own wording |
| 0.35    | FAO-56 water-stress threshold                       |

### Glossary

| Term                            | Meaning                                                           |
| ------------------------------- | ----------------------------------------------------------------- |
| **DACP**                  | District Agriculture Contingency Plan (ICAR-CRIDA)                |
| **BAO**                   | Block Agriculture Officer                                         |
| **JJAS**                  | June–September, the southwest monsoon season                     |
| **Onset**                 | Monsoon arrival.**Only IMD declares it. Ankur never does.** |
| **Dry spell**             | ≥5 consecutive days below 2.5 mm                                 |
| **Block**                 | Administrative unit below a district                              |
| **AWC**                   | Available Water Capacity — how much water the root zone holds    |
| **ET0**                   | Reference evapotranspiration                                      |
| **BSS**                   | Brier Skill Score, vs climatology                                 |
| **ECE**                   | Expected Calibration Error                                        |
| **Cost–loss ratio (α)** | Cost of acting ÷ loss avoided                                    |
| **ABSTAIN**               | Say nothing. The default and most common output.                  |
| **MISO/MJO**              | Intraseasonal oscillations driving subseasonal predictability     |
| **ENSO / ONI**            | El Niño–Southern Oscillation index                              |
