from __future__ import annotations

from uuid import UUID

from ankur_domain.services import RuleNotFoundError, RuleService
from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_rule_service

router = APIRouter(tags=["rules"])


@router.get("/rules")
async def list_rules(
    review_status: ReviewStatus | None = Query(default=None),
    district: str | None = Query(default=None),
    advisory_eligible: bool = Query(default=False),
    service: RuleService = Depends(get_rule_service),
) -> list[DACPRule]:
    if advisory_eligible:
        return await service.list_advisory_eligible(district=district)
    return await service.list(review_status=review_status, district=district)


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: UUID, service: RuleService = Depends(get_rule_service)) -> DACPRule:
    try:
        return await service.get(rule_id)
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail="rule not found") from exc


@router.get("/rules/{rule_id}/citation")
async def get_rule_citation(
    rule_id: UUID, service: RuleService = Depends(get_rule_service)
) -> Citation:
    try:
        return await service.citation_for(rule_id)
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail="rule not found") from exc
