from __future__ import annotations

from uuid import UUID

from ankur_domain.services import ReviewService, RuleNotApprovableError, RuleNotFoundError
from ankur_schemas.rule import DACPRule
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_review_service

router = APIRouter(tags=["review"])


class ApproveRequest(BaseModel):
    reviewed_by: str


class RejectRequest(BaseModel):
    reviewed_by: str
    reason: str | None = None


@router.get("/review-queue")
async def review_queue(service: ReviewService = Depends(get_review_service)) -> list[DACPRule]:
    return await service.review_queue()


@router.post("/rules/{rule_id}/approve")
async def approve_rule(
    rule_id: UUID, body: ApproveRequest, service: ReviewService = Depends(get_review_service)
) -> DACPRule:
    try:
        return await service.approve(rule_id, reviewed_by=body.reviewed_by)
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail="rule not found") from exc
    except RuleNotApprovableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/rules/{rule_id}/reject")
async def reject_rule(
    rule_id: UUID, body: RejectRequest, service: ReviewService = Depends(get_review_service)
) -> DACPRule:
    try:
        return await service.reject(rule_id, reviewed_by=body.reviewed_by, reason=body.reason)
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail="rule not found") from exc
