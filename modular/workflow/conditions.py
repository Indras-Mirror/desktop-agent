"""
Structured-condition evaluation for the workflow DSL.

13 documented ops, injection-safe (no eval, no exec).
Operands are template-resolved against the scope first.

Mirrors open-cowork's conditions.ts semantics exactly.
"""

from typing import Any, Union

from .template import resolve_template, TemplateScope
from .types import Condition


def _as_number(v: Any) -> Union[float, None]:
    """Coerce to a finite number, accepting numeric strings; None otherwise."""
    if isinstance(v, (int, float)):
        if v != v:  # NaN check
            return None
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return None


def _is_equal(a: Any, b: Any) -> bool:
    """Strict-ish equality: same-type primitives compare with ==; objects by JSON."""
    if a is b:
        return True
    if a is None or b is None:
        return False
    if type(a) is not type(b):
        return False
    if isinstance(a, (dict, list)):
        import json
        try:
            return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        except (TypeError, ValueError):
            return False
    return a == b


def evaluate_condition(cond: Condition, scope: TemplateScope) -> bool:
    """Evaluate a structured condition against a scope.
    Unknown ops raise ValueError (validation should have rejected them earlier).
    """
    op = cond.op

    if op in ("eq", "ne", "lt", "gt", "lte", "gte", "contains"):
        # Binary ops
        left = resolve_template(cond.left, scope)
        right = resolve_template(cond.right, scope)

        if op == "eq":
            return _is_equal(left, right)
        elif op == "ne":
            return not _is_equal(left, right)
        elif op in ("lt", "gt", "lte", "gte"):
            l = _as_number(left)
            r = _as_number(right)
            if l is None or r is None:
                return False
            if op == "lt":
                return l < r
            elif op == "gt":
                return l > r
            elif op == "lte":
                return l <= r
            elif op == "gte":
                return l >= r
        elif op == "contains":
            if isinstance(left, str):
                return str(right) in left
            if isinstance(left, list):
                return any(_is_equal(item, right) for item in left)
            return False

    elif op in ("truthy", "falsy", "exists"):
        # Unary value ops
        value = resolve_template(cond.value, scope)
        if op == "truthy":
            return bool(value)
        elif op == "falsy":
            return not bool(value)
        elif op == "exists":
            return value is not None

    elif op in ("and", "or"):
        # Logical ops
        if cond.conditions is None:
            raise ValueError(f"'{op}' requires a non-empty conditions list")
        if op == "and":
            return all(evaluate_condition(c, scope) for c in cond.conditions)
        elif op == "or":
            return any(evaluate_condition(c, scope) for c in cond.conditions)

    elif op == "not":
        if cond.condition is None:
            raise ValueError("'not' requires a condition")
        return not evaluate_condition(cond.condition, scope)

    raise ValueError(f"Unknown condition op: {op}")
