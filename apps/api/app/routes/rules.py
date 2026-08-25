from __future__ import annotations

from uuid import UUID

from ankur_domain.services import RuleNotFoundError, RuleService
from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_rule_service, paginated

router = APIRouter(tags=["rules"])


@router.get("/rules")
async def list_rules(
    review_status: ReviewStatus | None = Query(default=None),
    district: str | None = Query(default=None),
    state: str | None = Query(default=None),
    advisory_eligible: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
    service: RuleService = Depends(get_rule_service),
) -> list[DACPRule] | dict[str, object]:
    if advisory_eligible:
        fetch = lambda **kw: service.list_advisory_eligible(  # noqa: E731
            district=district, state=state, **kw
        )
    else:
        fetch = lambda **kw: service.list(  # noqa: E731
            review_status=review_status, district=district, state=state, **kw
        )
    return await paginated(fetch, limit=limit, offset=offset)


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
