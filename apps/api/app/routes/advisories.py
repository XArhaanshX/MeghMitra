from __future__ import annotations

from uuid import UUID

from ankur_geo import (
    RegionResolutionError,
    resolve_region,
    state_by_code,
    states_with_district_name,
)
from ankur_schemas.advisory import Advisory, TriggerEvent
from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode, DrySpellForecast, MoistureState
from ankur_schemas.rule import DACPRule
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from trigger_engine.decision import DEFAULT_COST_LOSS_RATIO

from app.advisory import AdvisoryEmissionService, EmissionResult
from app.deps import get_advisory_service, paginated

router = APIRouter(tags=["advisories"])


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "state": "Haryana",
                    "district": "Sirsa",
                    "crop_already_sown": True,
                    "cost_loss_ratio": 0.35,
                    "moisture": {
                        "block_id": "sirsa-block-1",
                        "as_of": "2020-07-15",
                        "soil_moisture_fraction": 0.2,
                        "consecutive_dry_days": 10,
                        "days_since_sowing": 10,
                        "onset_delay_days": None,
                        "rain_3d_mm": 0,
                        "rain_3d_normal_mm": 10,
                    },
                    "forecast": {
                        "block_id": "sirsa-block-1",
                        "issued_on": "2020-07-15",
                        "lead_days": 14,
                        "probability": 0.8,
                        "climatological_rate": 0.2,
                        "model_version": "trigger-engine/0.1.0",
                    },
                },
                {
                    "state": "Karnataka",
                    "district": "Bijapur",
                    "crop_already_sown": False,
                    "cost_loss_ratio": 0.35,
                    "moisture": {
                        "block_id": "bijapur-block-1",
                        "as_of": "2020-07-15",
                        "soil_moisture_fraction": 0.2,
                        "consecutive_dry_days": 10,
                        "days_since_sowing": 10,
                        "onset_delay_days": None,
                        "rain_3d_mm": 0,
                        "rain_3d_normal_mm": 10,
                    },
                    "forecast": {
                        "block_id": "bijapur-block-1",
                        "issued_on": "2020-07-15",
                        "lead_days": 14,
                        "probability": 0.8,
                        "climatological_rate": 0.2,
                        "model_version": "trigger-engine/0.1.0",
                    },
                },
            ]
        }
    )

    district: str
    state: str | None = Field(
        default=None,
        description=(
            "State the district belongs to. Required if `district`'s name is "
            "ingested for more than one state (e.g. 'Bijapur' -- Karnataka and "
            "Chhattisgarh both have one); optional otherwise, in which case it "
            "is resolved automatically."
        ),
    )
    moisture: MoistureState
    forecast: DrySpellForecast
    cost_loss_ratio: float = Field(default=DEFAULT_COST_LOSS_RATIO, gt=0.0, lt=1.0)
    crop_already_sown: bool = False


class EvaluateResponse(BaseModel):
    action: str
    detected_condition: ConditionCode | None
    abstain_reasons: list[str]
    decision_reason: str | None
    threshold: float | None
    probability: float
    rule: DACPRule | None
    citation: Citation | None
    trigger_event_id: UUID


def _to_response(result: EmissionResult) -> EvaluateResponse:
    decision = result.decision
    return EvaluateResponse(
        action=result.action.value,
        detected_condition=result.detected_condition,
        abstain_reasons=result.abstain_reasons,
        decision_reason=None if decision is None else decision.reason,
        threshold=None if decision is None else decision.threshold,
        probability=result.event.payload["forecast"]["probability"],
        rule=result.rule,
        citation=result.citation,
        trigger_event_id=result.event.id,
    )


def _resolve_state(district: str, state: str | None) -> str:
    """Resolve the state to scope `district`'s rule lookup to.

    Never guesses: an explicit `state` is validated against the ingested
    corpus via `resolve_region` (raises with the correct state name(s) if
    `district` belongs to a *different* state); an omitted `state` is only
    auto-resolved when the district name is unambiguous nationally.
    """
    if state is not None:
        try:
            return resolve_region(state, district).state.name
        except RegionResolutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    codes = states_with_district_name(district)
    if len(codes) == 0:
        raise HTTPException(
            status_code=422, detail=f"no plan for district {district!r} in any state"
        )
    if len(codes) > 1:
        names = ", ".join(
            sorted(match.name for code in codes if (match := state_by_code(code)) is not None)
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"district {district!r} is ingested for more than one state ({names}); "
                "pass 'state' to disambiguate"
            ),
        )
    resolved = state_by_code(codes[0])
    assert resolved is not None  # `codes` came from `states_with_district_name`
    return resolved.name


@router.post("/advisories", status_code=201)
async def evaluate_advisory(
    body: EvaluateRequest, service: AdvisoryEmissionService = Depends(get_advisory_service)
) -> EvaluateResponse:
    state = _resolve_state(body.district, body.state)
    result = await service.evaluate(
        state=state,
        district=body.district,
        moisture=body.moisture,
        forecast=body.forecast,
        cost_loss_ratio=body.cost_loss_ratio,
        crop_already_sown=body.crop_already_sown,
    )
    return _to_response(result)


@router.get("/advisories")
async def list_advisories(
    state: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
    service: AdvisoryEmissionService = Depends(get_advisory_service),
) -> list[Advisory] | dict[str, object]:
    return await paginated(
        lambda **kw: service.list_advisories(state=state, **kw), limit=limit, offset=offset
    )



@router.get("/trigger-events")
async def list_trigger_events(
    state: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
    service: AdvisoryEmissionService = Depends(get_advisory_service),
) -> list[TriggerEvent] | dict[str, object]:
    return await paginated(
        lambda **kw: service.list_events(state=state, **kw), limit=limit, offset=offset
    )
