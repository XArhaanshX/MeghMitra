"""Wires the trigger engine to persistence.

Lives in `apps/api` (not `trigger_engine` or `ankur_domain`) for the same
reason `IngestionService` lives here: this package is allowed to import both
siblings. `packages/` must not import `trigger_engine`, and `trigger_engine`
must not write to the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ankur_domain.policies import citation_appears_on_page
from ankur_domain.repositories import (
    AdvisoryRepository,
    DocumentRepository,
    TriggerEventRepository,
)
from ankur_domain.services import RuleService
from ankur_schemas.advisory import Advisory, TriggerEvent
from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode, DrySpellForecast, MoistureState
from ankur_schemas.rule import DACPRule
from trigger_engine.conditions import detect_condition
from trigger_engine.decision import AdvisoryAction, Decision
from trigger_engine.pipeline import emit_advisory


@dataclass(frozen=True, slots=True)
class EmissionResult:
    """One evaluation, ready to return over HTTP."""

    action: AdvisoryAction
    detected_condition: ConditionCode | None
    abstain_reasons: list[str]
    decision: Decision | None
    rule: DACPRule | None
    event: TriggerEvent
    advisory: Advisory | None

    @property
    def citation(self) -> Citation | None:
        return None if self.rule is None else self.rule.citation


@dataclass(slots=True)
class AdvisoryEmissionService:
    rules: RuleService
    events: TriggerEventRepository
    advisories: AdvisoryRepository
    documents: DocumentRepository | None = None

    async def _page_count(self, rules: list[DACPRule]) -> int | None:
        ids = {rule.document_id for rule in rules if rule.document_id is not None}
        if self.documents is None or len(ids) != 1:
            return None
        document = await self.documents.get(next(iter(ids)))
        return None if document is None else document.page_count

    async def _page_text(self, rule: DACPRule) -> str | None:
        if self.documents is None or rule.document_id is None:
            return None
        page = await self.documents.get_page(rule.document_id, rule.citation.page)
        return None if page is None else page.text

    async def evaluate(
        self,
        *,
        district: str,
        moisture: MoistureState,
        forecast: DrySpellForecast,
        cost_loss_ratio: float,
        crop_already_sown: bool,
    ) -> EmissionResult:
        """Retrieve an approved rule matching the detected condition, or ABSTAIN.

        Candidate rules are already filtered to `is_advisory_eligible` — pending,
        rejected, and uncited rows never reach `emit_advisory`. The probability
        cannot conjure a rule; a matched rule cannot fire without
        `can_emit_advisory` returning true.
        """
        candidates = await self.rules.list_advisory_eligible(district=district)
        detected = detect_condition(moisture)
        action, decision, rule, reasons = emit_advisory(
            moisture,
            forecast,
            candidates,
            cost_loss_ratio=cost_loss_ratio,
            crop_already_sown=crop_already_sown,
            document_page_count=await self._page_count(candidates),
        )
        if rule is not None:
            ok, why = citation_appears_on_page(rule.citation, await self._page_text(rule))
            if not ok:
                action = AdvisoryAction.ABSTAIN
                decision = None
                rule = None
                reasons = [why or "citation source_text does not appear on the cited page"]

        now = datetime.now(UTC)
        event = TriggerEvent(
            block_key=moisture.block_id,
            rule_id=None if rule is None else rule.id,
            detected_at=now,
            condition=None if detected is None else detected.value,
            reasons=reasons,
            payload={
                "district": district,
                "action": action.value,
                "moisture": moisture.model_dump(mode="json"),
                "forecast": forecast.model_dump(mode="json"),
                "decision": None
                if decision is None
                else {
                    "reason": decision.reason,
                    "threshold": decision.threshold,
                    "probability": decision.probability,
                },
            },
        )
        await self.events.add(event)

        advisory: Advisory | None = None
        if action is not AdvisoryAction.ABSTAIN:
            advisory = Advisory(
                trigger_event_id=event.id,
                rule_id=None if rule is None else rule.id,
                generated_at=now,
                action=action.value,
                reason=None if decision is None else decision.reason,
                channel="api",
            )
            await self.advisories.add(advisory)

        return EmissionResult(
            action=action,
            detected_condition=detected,
            abstain_reasons=reasons,
            decision=decision,
            rule=rule,
            event=event,
            advisory=advisory,
        )

    async def list_events(self) -> list[TriggerEvent]:
        return await self.events.list()

    async def list_advisories(self) -> list[Advisory]:
        return await self.advisories.list()
