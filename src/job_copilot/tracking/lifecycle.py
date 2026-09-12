"""Lifecycle transition rules and status derivation logic."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from job_copilot.tracking.models import ApplicationEvent, ApplicationLifecycleStatus
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Active pipeline stage ordering for progression validation
STAGE_ORDER = {
    ApplicationLifecycleStatus.DISCOVERED: 1,
    ApplicationLifecycleStatus.RECOMMENDED: 2,
    ApplicationLifecycleStatus.PREPARED: 3,
    ApplicationLifecycleStatus.READY_FOR_REVIEW: 4,
    ApplicationLifecycleStatus.MANUAL_ACTION_REQUIRED: 4,
    ApplicationLifecycleStatus.SUBMISSION_UNVERIFIED: 5,
    ApplicationLifecycleStatus.SUBMITTED: 6,
    ApplicationLifecycleStatus.ACKNOWLEDGED: 7,
    ApplicationLifecycleStatus.RECRUITER_RESPONSE: 8,
    ApplicationLifecycleStatus.ASSESSMENT: 9,
    ApplicationLifecycleStatus.INTERVIEW: 10,
    ApplicationLifecycleStatus.FINAL_ROUND: 11,
}

# Outcome states (results of applications)
OUTCOME_STAGES = {
    ApplicationLifecycleStatus.OFFER,
    ApplicationLifecycleStatus.ACCEPTED,
    ApplicationLifecycleStatus.REJECTED,
    ApplicationLifecycleStatus.WITHDRAWN,
    ApplicationLifecycleStatus.EXPIRED,
}

# Archive state (final inactive tracking state)
ARCHIVE_STAGES = {
    ApplicationLifecycleStatus.CLOSED,
}


class LifecycleValidator:
    """Validates lifecycle status transitions and derives current state from event logs."""

    @classmethod
    def validate_transition(
        cls,
        current: Optional[ApplicationLifecycleStatus],
        target: ApplicationLifecycleStatus,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate whether a transition from current -> target is valid.
        Returns (is_valid, warning_or_error_message).

        Rules:
          - Initial (current is None): Any status is valid.
          - Idempotent (current == target): Always valid (e.g. repeated interview rounds).
          - Archived (current == CLOSED): Closed applications cannot be transitioned out of CLOSED.
          - Outcome (current in OUTCOME_STAGES):
              * Can transition to CLOSED (archiving).
              * OFFER can transition to ACCEPTED, REJECTED, WITHDRAWN, EXPIRED, CLOSED.
              * ACCEPTED can transition to WITHDRAWN or CLOSED.
              * Other outcome states (REJECTED, WITHDRAWN, EXPIRED) can transition to CLOSED.
          - Active (current in STAGE_ORDER):
              * Can transition to any outcome state (OFFER, ACCEPTED, REJECTED, WITHDRAWN, EXPIRED) or CLOSED.
              * Can progress to a higher or equal active stage.
              * Regressions to earlier active stages are disallowed.
              * Skipping stages is permitted with a fast-track warning.
        """
        if current is None:
            return True, None

        if current == target:
            return True, None

        # 1. Archived state is final
        if current in ARCHIVE_STAGES:
            return False, f"Cannot transition from archived status '{current.value}' to '{target.value}'."

        # 2. Outcome states transitions
        if current in OUTCOME_STAGES:
            if target in ARCHIVE_STAGES:
                return True, None
            if current == ApplicationLifecycleStatus.OFFER:
                if target in [
                    ApplicationLifecycleStatus.ACCEPTED,
                    ApplicationLifecycleStatus.REJECTED,
                    ApplicationLifecycleStatus.WITHDRAWN,
                    ApplicationLifecycleStatus.EXPIRED,
                ]:
                    return True, None
            elif current == ApplicationLifecycleStatus.ACCEPTED:
                if target == ApplicationLifecycleStatus.WITHDRAWN:
                    return True, None

            return False, f"Cannot transition from outcome status '{current.value}' to '{target.value}'."

        # 3. Active state transitioning to outcome or archive states
        if target in OUTCOME_STAGES or target in ARCHIVE_STAGES:
            return True, None

        # 4. Active -> Active progression
        curr_rank = STAGE_ORDER.get(current, 0)
        targ_rank = STAGE_ORDER.get(target, 0)

        if targ_rank < curr_rank:
            return False, f"Regression transition from '{current.value}' back to earlier stage '{target.value}' is disallowed."

        # Check for skipped intermediate stages (emit warning rather than hard blocking)
        if targ_rank > curr_rank + 2:
            warning = f"Transition skipped intermediate stages ({current.value} -> {target.value}). Allowed as fast-track."
            return True, warning

        return True, None

    @classmethod
    def derive_current_status(
        cls,
        events: List[ApplicationEvent],
    ) -> Tuple[ApplicationLifecycleStatus, Optional[datetime]]:
        """
        Derive current lifecycle status and timestamp from sorted events list.
        """
        if not events:
            return ApplicationLifecycleStatus.DISCOVERED, None

        # Sort events chronologically by timestamp, handling naive and aware datetimes safely
        sorted_events = sorted(
            events,
            key=lambda e: e.timestamp if e.timestamp.tzinfo is not None else e.timestamp.replace(tzinfo=timezone.utc),
        )
        latest_event = sorted_events[-1]
        return latest_event.event_type, latest_event.timestamp
