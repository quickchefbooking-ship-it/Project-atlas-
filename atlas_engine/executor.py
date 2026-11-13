import ast
import math
import operator
import time
from typing import Any

from .config import USE_PAID_AI

MAX_EXPRESSION_CHARS = 256
MAX_NUMBER_MAGNITUDE = 1e15
MAX_AST_NODES = 128

_ALLOWED = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _checked_number(value: Any) -> int | float:
    """Keep arithmetic results finite, real and within the executor's numeric budget."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Only real numeric results are permitted")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numeric values are not permitted")
    if abs(value) > MAX_NUMBER_MAGNITUDE:
        raise ValueError("Number exceeds the supported range")
    return value


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("Local execution deadline exceeded")


def _safe_math(node, deadline: float | None = None):
    _check_deadline(deadline)
    if isinstance(node, ast.Expression):
        return _safe_math(node.body, deadline)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return _checked_number(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        left, right = _safe_math(node.left, deadline), _safe_math(node.right, deadline)
        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise ValueError("Exponent is too large")
        value = _ALLOWED[type(node.op)](left, right)
        return _checked_number(value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _checked_number(_ALLOWED[type(node.op)](_safe_math(node.operand, deadline)))
    raise ValueError("Only basic arithmetic is permitted")


def safe_execute_local(task: dict[str, Any]) -> dict[str, Any]:
    description = str(task.get("description", "")).strip()
    if not description:
        raise ValueError("Task description is empty")
    if len(description) > MAX_EXPRESSION_CHARS:
        raise ValueError("Arithmetic expression exceeds the maximum permitted length")
    deadline = task.get("_execution_deadline_monotonic")
    if deadline is not None:
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
            raise ValueError("Execution deadline must be a finite monotonic timestamp")
        _check_deadline(float(deadline))
    try:
        expression = ast.parse(description, mode="eval")
        if sum(1 for _ in ast.walk(expression)) > MAX_AST_NODES:
            raise ValueError("Arithmetic expression exceeds the maximum AST complexity")
        value = _safe_math(expression, float(deadline) if deadline is not None else None)
    except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Task is not a supported arithmetic expression") from exc
    return {"type": "safe_math", "value": value}


class LocalTaskExecutor:
    def __init__(self, provider: str | None = None):
        self.provider = provider or "local"
        if self.provider != "local" and not USE_PAID_AI:
            raise RuntimeError("Paid AI providers are disabled.")
        if self.provider != "local":
            raise RuntimeError("External AI providers are not implemented in this build.")

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        if self.provider != "local":
            raise ValueError("Unsupported provider")
        return safe_execute_local(task)
