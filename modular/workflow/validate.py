"""
Structural validation of a workflow definition.

Mirrors open-cowork's validate.ts with desktop-agent-specific limits and
the additional wait_for step type.

Limits:
    - Step IDs match ^[A-Za-z0-9_-]{1,64}$ and are unique across the whole tree
    - ≤200 steps total (counting every nested step), nesting ≤8 levels deep
    - parallel: ≤16 branches; no human_approval/succeed/fail/wait_for inside
    - retry.max_attempts: integer 1..20
    - loop: exactly one of count | while
    - save_as must not be 'inputs' or 'vars'
    - DSL version 2026-06-01: 10 step types, 13 condition ops
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    STEP_TYPES,
    CONDITION_OPS,
    BINARY_OPS,
    UNARY_VALUE_OPS,
    Condition,
)

DSL_VERSION = "2026-06-01"
MAX_TOTAL_STEPS = 200
MAX_NESTING_DEPTH = 8
MAX_PARALLEL_BRANCHES = 16
RETRY_ATTEMPTS_MIN = 1
RETRY_ATTEMPTS_MAX = 20
RESERVED_SAVE_AS = ("inputs", "vars")

STEP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ValidationIssue:
    def __init__(self, path: str, code: str, message: str):
        self.path = path
        self.code = code
        self.message = message

    def __repr__(self):
        return f"ValidationIssue({self.path!r}, {self.code!r}, {self.message!r})"

    def __eq__(self, other):
        if not isinstance(other, ValidationIssue):
            return False
        return (self.path == other.path and self.code == other.code
                and self.message == other.message)


class ValidationResult:
    def __init__(self, valid: bool, issues: List[ValidationIssue]):
        self.valid = valid
        self.issues = issues

    def __repr__(self):
        return f"ValidationResult(valid={self.valid}, issues={len(self.issues)})"


_VALID_ISSUE_CODES = frozenset({
    "MISSING_STEPS", "INVALID_STEP", "INVALID_ID", "DUPLICATE_ID",
    "UNKNOWN_TYPE", "MISSING_FIELD", "INVALID_FIELD",
    "TOO_MANY_STEPS", "TOO_DEEP", "TOO_MANY_BRANCHES",
    "INVALID_RETRY", "INVALID_LOOP", "INVALID_WAIT_FOR",
    "FORBIDDEN_IN_PARALLEL", "RESERVED_SAVE_AS", "INVALID_CONDITION",
})


def _validate_condition(cond: Any, path: str, issues: List[ValidationIssue]) -> None:
    """Validate a condition object structure."""
    if not isinstance(cond, dict):
        issues.append(ValidationIssue(path, "INVALID_CONDITION",
                                       "Condition must be an object"))
        return

    op = cond.get("op")
    if not isinstance(op, str) or op not in CONDITION_OPS:
        issues.append(ValidationIssue(
            f"{path}.op", "INVALID_CONDITION",
            f"Unknown condition op '{op}' "
            f"(expected one of {sorted(CONDITION_OPS)})"
        ))
        return

    if op in BINARY_OPS:
        if "left" not in cond or "right" not in cond:
            issues.append(ValidationIssue(
                path, "INVALID_CONDITION",
                f"'{op}' requires left and right"
            ))
    elif op in UNARY_VALUE_OPS:
        if "value" not in cond:
            issues.append(ValidationIssue(
                path, "INVALID_CONDITION",
                f"'{op}' requires value"
            ))
    elif op in ("and", "or"):
        sub_conds = cond.get("conditions")
        if not isinstance(sub_conds, list) or len(sub_conds) == 0:
            issues.append(ValidationIssue(
                f"{path}.conditions", "INVALID_CONDITION",
                f"'{op}' requires a non-empty conditions array"
            ))
        else:
            for i, sub in enumerate(sub_conds):
                _validate_condition(sub, f"{path}.conditions[{i}]", issues)
    elif op == "not":
        sub = cond.get("condition")
        if not isinstance(sub, dict):
            issues.append(ValidationIssue(
                path, "INVALID_CONDITION",
                "'not' requires condition"
            ))
        else:
            _validate_condition(sub, f"{path}.condition", issues)


class _WalkContext:
    """Mutable context carried through the recursive walk."""
    def __init__(self):
        self.issues: List[ValidationIssue] = []
        self.seen_ids: Dict[str, str] = {}
        self.total_steps: int = 0
        self.inside_parallel: bool = False


def _walk_steps(steps: Any, path: str, depth: int, ctx: _WalkContext) -> None:
    """Recursively validate a list of steps."""
    if not isinstance(steps, list):
        ctx.issues.append(ValidationIssue(
            path, "INVALID_STEP", "Expected an array of steps"
        ))
        return

    if depth > MAX_NESTING_DEPTH:
        ctx.issues.append(ValidationIssue(
            path, "TOO_DEEP",
            f"Steps nest at most {MAX_NESTING_DEPTH} levels deep"
        ))
        return

    for i, raw in enumerate(steps):
        p = f"{path}[{i}]"
        ctx.total_steps += 1

        if not isinstance(raw, dict):
            ctx.issues.append(ValidationIssue(
                p, "INVALID_STEP", "Step must be an object"
            ))
            continue

        step_id = raw.get("id", "")
        if not isinstance(step_id, str) or not STEP_ID_RE.match(step_id):
            ctx.issues.append(ValidationIssue(
                f"{p}.id", "INVALID_ID",
                f"Step id must match ^[A-Za-z0-9_-]{{1,64}}$ (got '{step_id}')"
            ))
        elif step_id in ctx.seen_ids:
            ctx.issues.append(ValidationIssue(
                f"{p}.id", "DUPLICATE_ID",
                f"Duplicate step id '{step_id}' "
                f"(first used at {ctx.seen_ids[step_id]})"
            ))
        else:
            ctx.seen_ids[step_id] = p

        step_type = raw.get("type", "")
        if not isinstance(step_type, str) or step_type not in STEP_TYPES:
            ctx.issues.append(ValidationIssue(
                f"{p}.type", "UNKNOWN_TYPE",
                f"Unknown step type '{step_type}'"
            ))
            continue

        # Forbidden inside parallel branches
        if ctx.inside_parallel and step_type in (
            "human_approval", "succeed", "fail", "wait_for"
        ):
            ctx.issues.append(ValidationIssue(
                p, "FORBIDDEN_IN_PARALLEL",
                f"'{step_type}' is not allowed inside a parallel branch"
            ))

        if step_type == "task":
            task_text = raw.get("task", "")
            if not isinstance(task_text, str) or not task_text.strip():
                ctx.issues.append(ValidationIssue(
                    f"{p}.task", "MISSING_FIELD",
                    "'task' requires a non-empty task string"
                ))
            save_as = raw.get("save_as")
            if save_as is not None:
                if not isinstance(save_as, str) or not STEP_ID_RE.match(save_as):
                    ctx.issues.append(ValidationIssue(
                        f"{p}.save_as", "INVALID_FIELD",
                        "save_as must be a short identifier"
                    ))
                elif save_as in RESERVED_SAVE_AS:
                    ctx.issues.append(ValidationIssue(
                        f"{p}.save_as", "RESERVED_SAVE_AS",
                        f"save_as must not be '{save_as}' (reserved namespace)"
                    ))

        elif step_type in ("assert", "if"):
            cond = raw.get("condition")
            if not isinstance(cond, dict):
                ctx.issues.append(ValidationIssue(
                    f"{p}.condition", "MISSING_FIELD",
                    f"'{step_type}' requires a condition"
                ))
            else:
                _validate_condition(cond, f"{p}.condition", ctx.issues)

            if step_type == "if":
                then_steps = raw.get("then")
                if not isinstance(then_steps, list):
                    ctx.issues.append(ValidationIssue(
                        f"{p}.then", "MISSING_FIELD",
                        "'if' requires a then branch"
                    ))
                else:
                    _walk_steps(then_steps, f"{p}.then", depth + 1, ctx)
                else_steps = raw.get("else")
                if isinstance(else_steps, list):
                    _walk_steps(else_steps, f"{p}.else", depth + 1, ctx)

        elif step_type == "loop":
            has_count = "count" in raw
            has_while = "while" in raw
            if has_count == has_while:
                ctx.issues.append(ValidationIssue(
                    p, "INVALID_LOOP",
                    "'loop' requires exactly one of count | while"
                ))
            if has_count:
                count = raw.get("count")
                if not isinstance(count, int) or count < 0:
                    ctx.issues.append(ValidationIssue(
                        f"{p}.count", "INVALID_FIELD",
                        "count must be a non-negative integer"
                    ))
            if has_while:
                _validate_condition(raw["while"], f"{p}.while", ctx.issues)
            body = raw.get("body")
            if not isinstance(body, list):
                ctx.issues.append(ValidationIssue(
                    f"{p}.body", "MISSING_FIELD",
                    "'loop' requires a body"
                ))
            else:
                _walk_steps(body, f"{p}.body", depth + 1, ctx)

        elif step_type == "parallel":
            branches = raw.get("branches")
            if not isinstance(branches, list) or len(branches) == 0:
                ctx.issues.append(ValidationIssue(
                    f"{p}.branches", "MISSING_FIELD",
                    "'parallel' requires branches"
                ))
            else:
                if len(branches) > MAX_PARALLEL_BRANCHES:
                    ctx.issues.append(ValidationIssue(
                        f"{p}.branches", "TOO_MANY_BRANCHES",
                        f"parallel takes at most {MAX_PARALLEL_BRANCHES} branches "
                        f"(got {len(branches)})"
                    ))
                prev_parallel = ctx.inside_parallel
                ctx.inside_parallel = True
                for b, branch in enumerate(branches):
                    _walk_steps(branch, f"{p}.branches[{b}]", depth + 1, ctx)
                ctx.inside_parallel = prev_parallel

        elif step_type == "retry":
            max_attempts = raw.get("max_attempts", 0)
            if (not isinstance(max_attempts, int)
                    or max_attempts < RETRY_ATTEMPTS_MIN
                    or max_attempts > RETRY_ATTEMPTS_MAX):
                ctx.issues.append(ValidationIssue(
                    f"{p}.max_attempts", "INVALID_RETRY",
                    f"retry.max_attempts must be an integer "
                    f"{RETRY_ATTEMPTS_MIN}..{RETRY_ATTEMPTS_MAX}"
                ))
            body = raw.get("body")
            if not isinstance(body, list):
                ctx.issues.append(ValidationIssue(
                    f"{p}.body", "MISSING_FIELD",
                    "'retry' requires a body"
                ))
            else:
                _walk_steps(body, f"{p}.body", depth + 1, ctx)

        elif step_type == "wait_for":
            cond = raw.get("condition")
            if not isinstance(cond, dict):
                ctx.issues.append(ValidationIssue(
                    f"{p}.condition", "MISSING_FIELD",
                    "'wait_for' requires a condition"
                ))
            else:
                _validate_condition(cond, f"{p}.condition", ctx.issues)
            timeout_ms = raw.get("timeout_ms", 0)
            if not isinstance(timeout_ms, int) or timeout_ms < 0:
                ctx.issues.append(ValidationIssue(
                    f"{p}.timeout_ms", "INVALID_WAIT_FOR",
                    "timeout_ms must be a non-negative integer"
                ))
            poll_ms = raw.get("poll_ms", 0)
            if not isinstance(poll_ms, int) or poll_ms < 10:
                ctx.issues.append(ValidationIssue(
                    f"{p}.poll_ms", "INVALID_WAIT_FOR",
                    "poll_ms must be an integer >= 10"
                ))

        elif step_type in ("human_approval", "succeed", "fail"):
            # These types have no required fields beyond id and type.
            # human_approval may optionally have message and timeout_seconds.
            pass


def validate_workflow_definition(definition: Any) -> ValidationResult:
    """Validate a workflow definition. Returns every issue found (does not stop at the first)."""
    issues: List[ValidationIssue] = []

    if not isinstance(definition, dict):
        return ValidationResult(
            valid=False,
            issues=[ValidationIssue("", "MISSING_STEPS",
                                     "Definition must be an object")]
        )

    steps = definition.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        issues.append(ValidationIssue(
            "steps", "MISSING_STEPS",
            "Definition requires a non-empty steps array"
        ))
        return ValidationResult(valid=False, issues=issues)

    ctx = _WalkContext()
    _walk_steps(steps, "steps", 1, ctx)

    if ctx.total_steps > MAX_TOTAL_STEPS:
        issues.append(ValidationIssue(
            "steps", "TOO_MANY_STEPS",
            f"At most {MAX_TOTAL_STEPS} steps total (got {ctx.total_steps})"
        ))

    # Merge walk issues with top-level issues
    all_issues = issues + ctx.issues
    return ValidationResult(valid=len(all_issues) == 0, issues=all_issues)
