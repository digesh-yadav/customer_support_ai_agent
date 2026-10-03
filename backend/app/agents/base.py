import time
from dataclasses import dataclass, field


@dataclass
class AgentResult:
    agent: str
    ok: bool = True
    data: dict = field(default_factory=dict)
    summary: str = ""
    ms: int = 0


def timed(fn):
    """Run fn() and return (result, elapsed_ms)."""
    t = time.perf_counter()
    out = fn()
    return out, int((time.perf_counter() - t) * 1000)
