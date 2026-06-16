"""
Type definitions for the desktop-workflow DSL.

10 step types, 13 condition ops.
Mirrors open-cowork's type system, adapted for local-first desktop automation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

# ── Condition types ───────────────────────────────────────────────────────────

ConditionOp = Literal[
    "eq", "ne", "lt", "gt", "lte", "gte",
    "contains", "truthy", "falsy", "exists",
    "and", "or", "not",
]

CONDITION_OPS = frozenset({
    "eq", "ne", "lt", "gt", "lte", "gte",
    "contains", "truthy", "falsy", "exists",
    "and", "or", "not",
})

BINARY_OPS = frozenset({"eq", "ne", "lt", "gt", "lte", "gte", "contains"})
UNARY_VALUE_OPS = frozenset({"truthy", "falsy", "exists"})

# Recursive Condition type. We use a TypedDict-like approach via dataclass
# because Python lacks recursive type aliases cleanly.
# In practice, conditions are dicts from JSON; we validate structurally.

@dataclass
class Condition:
    """A structured condition. One of:
    - Binary: {op: eq|ne|lt|gt|lte|gte|contains, left, right}
    - Unary value: {op: truthy|falsy|exists, value}
    - Logic: {op: and|or, conditions: [...]}
    - Negation: {op: not, condition: {...}}
    """
    op: str
    left: Any = None
    right: Any = None
    value: Any = None
    conditions: Optional[List['Condition']] = None
    condition: Optional['Condition'] = None

    # Top-level fields that get resolved.
    # In practice, conditions come from JSON, so we store everything
    # extra in a dict for dynamic access.
    _extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> 'Condition':
        """Construct from a JSON-decoded dict, recursing into sub-conditions."""
        extra = {k: v for k, v in d.items() if k not in ("op", "left", "right", "value", "conditions", "condition")}
        cond = cls(
            op=d.get("op", ""),
            left=d.get("left"),
            right=d.get("right"),
            value=d.get("value"),
            conditions=None,
            condition=None,
            _extra=extra,
        )
        if isinstance(d.get("conditions"), list):
            cond.conditions = [cls.from_dict(c) for c in d["conditions"]]
        if isinstance(d.get("condition"), dict):
            cond.condition = cls.from_dict(d["condition"])
        return cond

    def to_dict(self) -> dict:
        d: dict = {"op": self.op}
        if self.left is not None:
            d["left"] = self.left
        if self.right is not None:
            d["right"] = self.right
        if self.value is not None:
            d["value"] = self.value
        if self.conditions is not None:
            d["conditions"] = [c.to_dict() for c in self.conditions]
        if self.condition is not None:
            d["condition"] = self.condition.to_dict()
        d.update(self._extra)
        return d


# ── Step types ────────────────────────────────────────────────────────────────

STEP_TYPES = frozenset({
    "task", "assert", "if", "loop", "parallel",
    "human_approval", "retry", "wait_for", "succeed", "fail",
})


@dataclass
class TaskStep:
    """Execute a desktop-agent command and bind its result."""
    id: str
    type: Literal["task"] = "task"
    task: str = ""  # The command text (e.g., "Open Firefox and navigate to Jira")
    save_as: Optional[str] = None  # Bind result under this name in scope
    # Optional: time limit for this task
    timeout_seconds: Optional[int] = None

    # Extra fields preserved from JSON
    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssertStep:
    """Fail the workflow if condition is false."""
    id: str
    type: Literal["assert"] = "assert"
    condition: Optional[Condition] = None
    message: Optional[str] = None

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IfStep:
    """Branch based on a condition."""
    id: str
    type: Literal["if"] = "if"
    condition: Optional[Condition] = None
    then: List['WorkflowStep'] = field(default_factory=list)
    else_: Optional[List['WorkflowStep']] = None

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopStep:
    """Loop n times or while condition holds."""
    id: str
    type: Literal["loop"] = "loop"
    count: Optional[int] = None
    while_: Optional[Condition] = None
    body: List['WorkflowStep'] = field(default_factory=list)
    max_iterations: Optional[int] = None

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelStep:
    """Run branches concurrently. Results share scope (last write wins on conflicts)."""
    id: str
    type: Literal["parallel"] = "parallel"
    branches: List[List['WorkflowStep']] = field(default_factory=list)

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HumanApprovalStep:
    """Pause until a human approves or rejects."""
    id: str
    type: Literal["human_approval"] = "human_approval"
    message: Optional[str] = None
    timeout_seconds: Optional[int] = None

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetryStep:
    """Retry body on failure up to max_attempts times."""
    id: str
    type: Literal["retry"] = "retry"
    body: List['WorkflowStep'] = field(default_factory=list)
    max_attempts: int = 3

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WaitForStep:
    """Poll the screen until a condition is met or timeout.

    NEW for desktop-agent: not in open-cowork's DSL.
    Re-checks screen state at poll_ms intervals.
    """
    id: str
    type: Literal["wait_for"] = "wait_for"
    condition: Optional[Condition] = None
    timeout_ms: int = 10000
    poll_ms: int = 500

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SucceedStep:
    """Explicit early success with optional output."""
    id: str
    type: Literal["succeed"] = "succeed"
    output: Optional[Dict[str, Any]] = None

    _extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FailStep:
    """Explicit early failure."""
    id: str
    type: Literal["fail"] = "fail"
    message: Optional[str] = None

    _extra: Dict[str, Any] = field(default_factory=dict)


# Union type for any step
WorkflowStep = Union[
    TaskStep,
    AssertStep,
    IfStep,
    LoopStep,
    ParallelStep,
    HumanApprovalStep,
    RetryStep,
    WaitForStep,
    SucceedStep,
    FailStep,
]


@dataclass
class WorkflowDefinition:
    """Top-level workflow: an ordered list of steps."""
    steps: List[WorkflowStep] = field(default_factory=list)
    output: Optional[Dict[str, Any]] = None  # Implicit succeed output template

    _extra: Dict[str, Any] = field(default_factory=dict)


# ── Runtime types ─────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    """Result of executing a task step."""
    status: str = "done"  # "done" | "failed"
    passed: bool = False
    result: Any = None  # Free-form result data
    error: Optional[str] = None
    # Timing
    duration_ms: int = 0
    # Screen context after the step (optional, for analysis)
    screen_summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "passed": self.passed,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class WorkflowGuards:
    """Safety limits for workflow execution."""
    max_iterations: Optional[int] = None  # Total loop iterations cap
    deadline_seconds: Optional[int] = None  # Wall-clock budget
    # No budget_cents — local-first, no billing


@dataclass
class WorkflowEvalEvent:
    """Event emitted during workflow execution."""
    type: str  # "step-start", "step-finish", "task-result", "awaiting-approval", etc.
    step_id: Optional[str] = None
    step_type: Optional[str] = None
    outcome: Optional[str] = None  # "ok" | "failed"
    result: Optional[StepResult] = None
    message: Optional[str] = None
    approved: Optional[bool] = None
    guard: Optional[str] = None


@dataclass
class WorkflowEvalResult:
    """Final result of workflow execution."""
    status: str  # "succeeded" | "failed"
    output: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None  # {code, message}
    iterations_used: int = 0
    bindings: Dict[str, Any] = field(default_factory=dict)


# ── Helpers for building steps from JSON ──────────────────────────────────────

_STEP_TYPE_MAP = {
    "task": TaskStep,
    "assert": AssertStep,
    "if": IfStep,
    "loop": LoopStep,
    "parallel": ParallelStep,
    "human_approval": HumanApprovalStep,
    "retry": RetryStep,
    "wait_for": WaitForStep,
    "succeed": SucceedStep,
    "fail": FailStep,
}


def step_from_dict(d: dict) -> WorkflowStep:
    """Build a typed step from a JSON-decoded dict, recursing into children."""
    step_type = d.get("type", "")
    cls = _STEP_TYPE_MAP.get(step_type)
    if cls is None:
        # Return a generic dict-like step for unknown types;
        # validation will catch and reject it.
        return TaskStep(id=d.get("id", "unknown"), type="task", task=str(d))

    kwargs = {"id": d.get("id", ""), "_extra": {}}

    # Store any keys not known to this step type in _extra
    known_keys = _KNOWN_KEYS.get(step_type, set()) | {"id", "type"}

    for k, v in d.items():
        if k not in known_keys:
            kwargs["_extra"][k] = v

    if step_type == "task":
        return TaskStep(
            id=d.get("id", ""),
            task=d.get("task", ""),
            save_as=d.get("save_as"),
            timeout_seconds=d.get("timeout_seconds"),
            _extra=kwargs.get("_extra", {}),
        )
    elif step_type == "assert":
        cond = Condition.from_dict(d["condition"]) if isinstance(d.get("condition"), dict) else None
        return AssertStep(id=d.get("id", ""), condition=cond, message=d.get("message"), _extra=kwargs.get("_extra", {}))
    elif step_type == "if":
        cond = Condition.from_dict(d["condition"]) if isinstance(d.get("condition"), dict) else None
        then_steps = [step_from_dict(s) for s in d.get("then", [])]
        else_steps = [step_from_dict(s) for s in d.get("else", [])] if d.get("else") else None
        return IfStep(id=d.get("id", ""), condition=cond, then=then_steps, else_=else_steps, _extra=kwargs.get("_extra", {}))
    elif step_type == "loop":
        while_cond = Condition.from_dict(d["while"]) if isinstance(d.get("while"), dict) else None
        body = [step_from_dict(s) for s in d.get("body", [])]
        return LoopStep(id=d.get("id", ""), count=d.get("count"), while_=while_cond, body=body,
                        max_iterations=d.get("max_iterations"), _extra=kwargs.get("_extra", {}))
    elif step_type == "parallel":
        branches = [[step_from_dict(s) for s in b] for b in d.get("branches", [])]
        return ParallelStep(id=d.get("id", ""), branches=branches, _extra=kwargs.get("_extra", {}))
    elif step_type == "human_approval":
        return HumanApprovalStep(id=d.get("id", ""), message=d.get("message"),
                                 timeout_seconds=d.get("timeout_seconds"), _extra=kwargs.get("_extra", {}))
    elif step_type == "retry":
        body = [step_from_dict(s) for s in d.get("body", [])]
        return RetryStep(id=d.get("id", ""), body=body, max_attempts=d.get("max_attempts", 3),
                         _extra=kwargs.get("_extra", {}))
    elif step_type == "wait_for":
        cond = Condition.from_dict(d["condition"]) if isinstance(d.get("condition"), dict) else None
        return WaitForStep(id=d.get("id", ""), condition=cond,
                           timeout_ms=d.get("timeout_ms", 10000),
                           poll_ms=d.get("poll_ms", 500),
                           _extra=kwargs.get("_extra", {}))
    elif step_type == "succeed":
        return SucceedStep(id=d.get("id", ""), output=d.get("output"), _extra=kwargs.get("_extra", {}))
    elif step_type == "fail":
        return FailStep(id=d.get("id", ""), message=d.get("message"), _extra=kwargs.get("_extra", {}))
    else:
        return TaskStep(id=d.get("id", "unknown"), task=str(d))


def workflow_from_dict(d: dict) -> WorkflowDefinition:
    """Build a WorkflowDefinition from a JSON-decoded dict."""
    steps = [step_from_dict(s) for s in d.get("steps", [])]
    return WorkflowDefinition(steps=steps, output=d.get("output"), _extra={
        k: v for k, v in d.items() if k not in ("steps", "output")
    })


# Known keys per step type (used by step_from_dict to separate _extra)
_KNOWN_KEYS: Dict[str, frozenset] = {
    "task": frozenset({"task", "save_as", "timeout_seconds"}),
    "assert": frozenset({"condition", "message"}),
    "if": frozenset({"condition", "then", "else"}),
    "loop": frozenset({"count", "while", "body", "max_iterations"}),
    "parallel": frozenset({"branches"}),
    "human_approval": frozenset({"message", "timeout_seconds"}),
    "retry": frozenset({"body", "max_attempts"}),
    "wait_for": frozenset({"condition", "timeout_ms", "poll_ms"}),
    "succeed": frozenset({"output"}),
    "fail": frozenset({"message"}),
}
