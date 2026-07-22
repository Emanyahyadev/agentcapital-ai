"""The resilience layer is load-bearing: these tests prove retries fire only
for transient failures, contracts stop garbage output, and the circuit
breaker opens after repeated exhaustion and recovers after cooldown."""

from pydantic import BaseModel

from src.agents.base import (
    BaseAgent,
    CircuitBreaker,
    ContractViolation,
    PermanentFailure,
    TransientFailure,
    classify,
)
from src.config.settings import Settings


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


class _Out(BaseModel):
    value: int


class FlakyAgent(BaseAgent):
    name = "flaky"
    output_key = "payload"
    output_model = _Out

    def __init__(self, settings, failures_before_success=0, error=None):
        super().__init__(settings)
        self.calls = 0
        self.failures_before_success = failures_before_success
        self.error = error if error is not None else TransientFailure("429")
        self.slept: list[float] = []

    def execute(self, state):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise self.error
        return {"payload": {"value": 42}}

    def _sleep(self, seconds):
        self.slept.append(seconds)


def fresh(agent_cls, *args, **kwargs):
    BaseAgent._breakers.clear()
    return agent_cls(*args, **kwargs)


def test_transient_failure_is_retried_then_succeeds():
    agent = fresh(FlakyAgent, make_settings(max_retries=3), failures_before_success=2)
    result = agent({})
    assert result["payload"] == {"value": 42}
    assert agent.calls == 3
    assert len(agent.slept) == 2  # backoff happened between attempts


def test_permanent_failure_is_never_retried():
    agent = fresh(
        FlakyAgent, make_settings(max_retries=3),
        failures_before_success=99, error=PermanentFailure("bad credentials"),
    )
    result = agent({})
    assert agent.calls == 1
    assert result["errors"][0]["error_type"] == "permanent"


def test_retries_exhaust_into_structured_error():
    agent = fresh(FlakyAgent, make_settings(max_retries=2), failures_before_success=99)
    result = agent({})
    assert agent.calls == 2
    err = result["errors"][0]
    assert err["agent"] == "flaky"
    assert err["error_type"] == "transient"
    assert err["attempts"] == 2


def test_contract_violation_blocks_bad_output():
    class GarbageAgent(FlakyAgent):
        name = "garbage"

        def execute(self, state):
            return {"payload": {"value": "not-an-int-at-all"}}

    agent = fresh(GarbageAgent, make_settings(max_retries=3))
    result = agent({})
    assert result["errors"][0]["error_type"] == "contract"


def test_classify_maps_vendor_errors():
    assert isinstance(classify(RuntimeError("429 RESOURCE_EXHAUSTED")), TransientFailure)
    assert isinstance(classify(RuntimeError("connection reset by peer")), TransientFailure)
    assert isinstance(classify(RuntimeError("invalid api key")), PermanentFailure)
    assert isinstance(classify(ContractViolation("x")), ContractViolation)


def test_circuit_breaker_opens_and_half_opens():
    t = {"now": 0.0}
    cb = CircuitBreaker(threshold=3, cooldown_s=60, clock=lambda: t["now"])
    for _ in range(3):
        assert cb.allow()
        cb.record_failure()
    assert cb.open and not cb.allow()  # open: fail fast
    t["now"] += 61
    assert cb.allow()  # half-open probe permitted
    cb.record_success()
    assert not cb.open  # recovered


def test_open_breaker_fails_fast_without_calling_execute():
    settings = make_settings(max_retries=1, circuit_breaker_threshold=1)
    agent = fresh(FlakyAgent, settings, failures_before_success=99)
    agent({})  # exhausts -> breaker opens
    calls_before = agent.calls
    result = agent({})  # breaker open -> no execute call
    assert agent.calls == calls_before
    assert "circuit breaker open" in result["errors"][0]["message"]
