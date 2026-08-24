from __future__ import annotations

from uuid import UUID

from ankur_schemas.advisory import Advisory, TriggerEvent
from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode, DrySpellForecast, MoistureState
from ankur_schemas.rule import DACPRule
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from trigger_engine.decision import DEFAULT_COST_LOSS_RATIO

from app.advisory import AdvisoryEmissionService, EmissionResult
from app.deps import get_advisory_service

router = APIRouter(tags=["advisories"])


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
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
                }
            ]
        }
    )

    district: str
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


@router.post("/advisories", status_code=201)
async def evaluate_advisory(
    body: EvaluateRequest, service: AdvisoryEmissionService = Depends(get_advisory_service)
) -> EvaluateResponse:
    result = await service.evaluate(
        district=body.district,
        moisture=body.moisture,
        forecast=body.forecast,
        cost_loss_ratio=body.cost_loss_ratio,
        crop_already_sown=body.crop_already_sown,
    )
    return _to_response(result)


@router.get("/advisories")
async def list_advisories(
    service: AdvisoryEmissionService = Depends(get_advisory_service),
) -> list[Advisory]:
    return await service.list_advisories()


@router.get("/trigger-events")
async def list_trigger_events(
    service: AdvisoryEmissionService = Depends(get_advisory_service),
) -> list[TriggerEvent]:
    return await service.list_events()
