"""
desktop-workflow: A deterministic workflow DSL for desktop-agent.

Inspired by open-cowork's workflow DSL, adapted for local-first desktop automation.
Composes desktop-agent commands (analyze, click, type, etc.) into recoverable,
approvable sequences with structured control flow.

Architecture:
    types.py      — Step/condition type definitions (dataclasses)
    template.py   — {{path}} dotted template resolver
    conditions.py — Structured condition evaluator (no eval(), injection-safe)
    validate.py   — Structural validation (limits, uniqueness, nesting)
    evaluator.py  — Deterministic interpreter with injected dependencies

Key differences from open-cowork:
    - No cost tracking (local-first, no billing)
    - task steps execute desktop-agent commands, not Coasty API calls
    - Added wait_for step type for screen-polling conditions
    - Python dataclasses instead of TypeScript interfaces
    - Same injection-safe condition model, same template system
"""

from .types import (
    ConditionOp,
    Condition,
    WorkflowStep,
    WorkflowDefinition,
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
    StepResult,
    WorkflowEvalEvent,
    WorkflowEvalResult,
    WorkflowGuards,
    STEP_TYPES,
    CONDITION_OPS,
    BINARY_OPS,
    UNARY_VALUE_OPS,
)
from .template import (
    TemplateScope,
    resolve_path,
    resolve_template,
    resolve_deep,
)
from .conditions import evaluate_condition
from .validate import (
    ValidationIssue,
    ValidationResult,
    validate_workflow_definition,
    DSL_VERSION,
    MAX_TOTAL_STEPS,
    MAX_NESTING_DEPTH,
    MAX_PARALLEL_BRANCHES,
    RETRY_ATTEMPTS_MIN,
    RETRY_ATTEMPTS_MAX,
    RESERVED_SAVE_AS,
)
from .evaluator import execute_workflow

__all__ = [
    # Types
    "ConditionOp",
    "Condition",
    "WorkflowStep",
    "WorkflowDefinition",
    "TaskStep",
    "AssertStep",
    "IfStep",
    "LoopStep",
    "ParallelStep",
    "HumanApprovalStep",
    "RetryStep",
    "WaitForStep",
    "SucceedStep",
    "FailStep",
    "StepResult",
    "WorkflowEvalEvent",
    "WorkflowEvalResult",
    "WorkflowGuards",
    "STEP_TYPES",
    "CONDITION_OPS",
    "BINARY_OPS",
    "UNARY_VALUE_OPS",
    # Template
    "TemplateScope",
    "resolve_path",
    "resolve_template",
    "resolve_deep",
    # Conditions
    "evaluate_condition",
    # Validation
    "ValidationIssue",
    "ValidationResult",
    "validate_workflow_definition",
    "DSL_VERSION",
    "MAX_TOTAL_STEPS",
    "MAX_NESTING_DEPTH",
    "MAX_PARALLEL_BRANCHES",
    "RETRY_ATTEMPTS_MIN",
    "RETRY_ATTEMPTS_MAX",
    "RESERVED_SAVE_AS",
    # Evaluator
    "execute_workflow",
]
