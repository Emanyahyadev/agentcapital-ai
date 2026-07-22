"""The resilience layer every agent inherits.

Three mechanisms, composed in ``BaseAgent.__call__``:

1. **Error taxonomy** — failures are classified transient / permanent /
   contract. Only transient failures are retried; a schema violation is
   never retried because the same input will fail the same way.
2. **Retry with exponential backoff + full jitter** — required in practice:
   the Gemini free tier rate-limits at ~10 requests/minute, so 429s are an
   expected operating condition, not an exception.
3. **Per-agent circuit breaker** — after N consecutive exhausted calls the
   breaker opens and the agent fails fast for a cooldown period, so a dead
   downstream (LLM outage, DB down) doesn't stall every run in retry loops.

Agents never raise into the graph. Failures become structured AgentError
records appended to ``state["errors"]``, and the orchestrator routes on them.
"""

import random
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from src.config.settings import Settings, get_settings
from src.core.contracts import AgentError
from src.core.state import PolarisState
from src.core.telemetry import collected_tokens, reset_tokens
from src.db.client import audit
from src.observability.logger import get_logger


class AgentFailure(Exception):
    """Base for classified failures raised inside agents."""


class TransientFailure(AgentFailure):
    """Worth retrying: rate limits, timeouts, 5xx, dropped connections."""


class PermanentFailure(AgentFailure):
    """Retrying cannot help: bad credentials, missing document, logic error."""


class ContractViolation(AgentFailure):
    """Output failed schema validation — the agent produced garbage."""


_TRANSIENT_MARKERS = (
    "429",
    "rate limit",
    "resource_exhausted",
    "resourceexhausted",
    "503",
    "500",
    "unavailable",
    "overloaded",
    "timeout",
    "timed out",
    "connection",
    "temporarily",
)


def classify(exc: Exception) -> AgentFailure:
    """Map an arbitrary exception onto the failure taxonomy by inspecting its
    text — vendor SDKs disagree on exception classes, but not on wording."""
    if isinstance(exc, AgentFailure):
        return exc
    text = f"{type(exc).__name__} {exc}".lower()
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return TransientFailure(str(exc))
    return PermanentFailure(f"{type(exc).__name__}: {exc}")


class CircuitBreaker:
    """Consecutive-failure breaker with cooldown-based half-open probes."""

    def __init__(self, threshold: int, cooldown_s: float, clock=time.monotonic):
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def open(self) -> bool:
        return self._opened_at is not None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if self._clock() - self._opened_at >= self.cooldown_s:
            return True  # half-open: let one probe through
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = self._clock()


class BaseAgent(ABC):
    """Subclasses implement ``execute`` and declare what they produce; the
    base class owns retries, the breaker, contract validation, and logging."""

    name: ClassVar[str] = "base"
    # When set, result[output_key] is validated through output_model before
    # it may enter shared state.
    output_key: ClassVar[str | None] = None
    output_model: ClassVar[type[BaseModel] | None] = None

    _breakers: ClassVar[dict[str, CircuitBreaker]] = {}

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.log = get_logger(agent=self.name)

    @property
    def breaker(self) -> CircuitBreaker:
        if self.name not in self._breakers:
            self._breakers[self.name] = CircuitBreaker(
                self.settings.circuit_breaker_threshold,
                self.settings.circuit_breaker_cooldown_s,
            )
        return self._breakers[self.name]

    @abstractmethod
    def execute(self, state: PolarisState) -> dict[str, Any]:
        """Do the work; return a partial state update."""

    def __call__(self, state: PolarisState) -> dict[str, Any]:
        if not self.breaker.allow():
            self.log.warning("circuit_open_fail_fast")
            return self._error_update("transient", "circuit breaker open — failing fast", 0)

        attempts = 0
        while True:
            attempts += 1
            reset_tokens()
            started = time.monotonic()
            try:
                result = self.execute(state)
                duration_ms = round((time.monotonic() - started) * 1000)
                self._validate_output(result)
                self.breaker.record_success()
                tokens = collected_tokens()
                self.log.info("agent_success", attempts=attempts,
                              duration_ms=duration_ms, tokens=tokens)
                # Real per-agent telemetry the console reads back: deterministic
                # agents legitimately report zero tokens.
                audit(state.get("run_id"), self.name, "agent_completed",
                      payload={"duration_ms": duration_ms, "tokens": tokens,
                               "attempts": attempts})
                return result
            except Exception as exc:  # noqa: BLE001 — boundary: classify everything
                failure = classify(exc)
                retryable = isinstance(failure, TransientFailure)
                if retryable and attempts < self.settings.max_retries:
                    delay = self._backoff_delay(attempts)
                    self.log.warning(
                        "agent_retry", attempt=attempts, delay_s=round(delay, 2),
                        error=str(failure),
                    )
                    self._sleep(delay)
                    continue

                self.breaker.record_failure()
                error_type = (
                    "contract" if isinstance(failure, ContractViolation)
                    else "transient" if retryable
                    else "permanent"
                )
                self.log.error("agent_failed", error_type=error_type,
                               attempts=attempts, error=str(failure))
                return self._error_update(error_type, str(failure), attempts)

    def _validate_output(self, result: dict[str, Any]) -> None:
        if self.output_key is None or self.output_model is None:
            return
        payload = result.get(self.output_key)
        if payload is None:
            raise ContractViolation(f"{self.name} produced no '{self.output_key}'")
        try:
            model = (
                payload if isinstance(payload, self.output_model)
                else self.output_model.model_validate(payload)
            )
        except ValidationError as exc:
            raise ContractViolation(f"{self.name} output failed contract: {exc}") from exc
        result[self.output_key] = model.model_dump(mode="json")

    def _error_update(self, error_type: str, message: str, attempts: int) -> dict[str, Any]:
        err = AgentError(
            agent=self.name, error_type=error_type, message=message, attempts=attempts
        )
        return {"errors": [err.model_dump()]}

    def _backoff_delay(self, attempt: int) -> float:
        # Full jitter: uniform(0, base * 2^attempt) — avoids thundering herds
        # when several runs hit the same rate limit simultaneously.
        return random.uniform(0, self.settings.retry_base_delay_s * (2**attempt))

    def _sleep(self, seconds: float) -> None:  # patchable in tests
        time.sleep(seconds)
