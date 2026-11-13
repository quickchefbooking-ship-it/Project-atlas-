import time

import pytest

from atlas_engine.executor import MAX_AST_NODES, safe_execute_local


def test_local_executor_accepts_live_monotonic_deadline():
    result = safe_execute_local({
        "description": "7 * 6",
        "_execution_deadline_monotonic": time.monotonic() + 2,
    })
    assert result == {"type": "safe_math", "value": 42}


def test_local_executor_rejects_expired_deadline():
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        safe_execute_local({
            "description": "1 + 1",
            "_execution_deadline_monotonic": time.monotonic() - 1,
        })


@pytest.mark.parametrize("deadline", [True, float("nan"), float("inf"), "soon"])
def test_local_executor_rejects_invalid_deadline_values(deadline):
    with pytest.raises(ValueError, match="finite monotonic timestamp"):
        safe_execute_local({
            "description": "1 + 1",
            "_execution_deadline_monotonic": deadline,
        })


def test_local_executor_bounds_ast_complexity():
    expression = "+".join(["1"] * (MAX_AST_NODES // 2 + 2))
    with pytest.raises(ValueError, match="AST complexity"):
        safe_execute_local({"description": expression})
