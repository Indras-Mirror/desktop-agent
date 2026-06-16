"""
Deterministic workflow evaluator for desktop-agent.

Synchronous execution (desktop-agent commands are local and blocking).
Uses injected-dependency pattern: the evaluator defines control flow,
the caller injects:
    - run_task: executes one desktop-agent command
    - on_approval: decides human_approval steps
    - on_event: receives stream of execution events
    - now: injectable clock (default time.time)

Adapted from open-cowork's evaluator.ts for local-first:
    - No cost tracking
    - Added wait_for step type (screen polling)
    - task steps call desktop-agent commands, not Coasty API
    - Fully synchronous (no asyncio needed)

Parallel branches execute via ThreadPoolExecutor for concurrency.
"""

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .types import (
    TaskStep,
    HumanApprovalStep,
    WorkflowDefinition,
    WorkflowGuards,
    WorkflowEvalEvent,
    WorkflowEvalResult,
    StepResult,
)
from .template import TemplateScope, resolve_template, resolve_deep
from .conditions import evaluate_condition
from .validate import validate_workflow_definition


# ── Internal control-flow signals ─────────────────────────────────────────

class _WorkflowTermination(Exception):
    """Signal to exit the workflow early (succeed/fail)."""
    def __init__(self, status, output=None, error=None):
        super().__init__(status)
        self.status = status
        self.output = output
        self.error = error


class _StepFailure(Exception):
    """A task step failed at the transport level."""
    def __init__(self, step_id, message):
        super().__init__(message)
        self.step_id = step_id
        self.message = message


# ── Callback signatures ───────────────────────────────────────────────────

# run_task receives the step definition + resolved task text, returns result
RunTaskFn = Callable[[TaskStep, str], StepResult]

# on_approval receives the step + resolved message, returns True=approve
ApprovalFn = Callable[[HumanApprovalStep, Optional[str]], bool]

# on_event receives execution events for streaming/logging
EventFn = Callable[[WorkflowEvalEvent], None]


# ── Main entry point ──────────────────────────────────────────────────────

def execute_workflow(
    definition,        # WorkflowDefinition or dict
    run_task,          # RunTaskFn
    inputs=None,       # Optional[Dict]
    guards=None,       # Optional[WorkflowGuards]
    on_approval=None,  # Optional[ApprovalFn]
    on_event=None,     # Optional[EventFn]
    now=None,          # Optional[Callable[[], float]]
):
    """Execute a workflow definition deterministically.

    Args:
        definition: WorkflowDefinition or plain dict (auto-converted)
        run_task: Function that executes a task step
        inputs: Workflow input parameters (accessible as {{inputs.key}})
        guards: Safety limits (max_iterations, deadline_seconds)
        on_approval: Human approval handler (None = auto-reject, fail closed)
        on_event: Event callback for streaming progress
        now: Injectable clock (default: time.time)

    Returns:
        WorkflowEvalResult with status, output, bindings, and (if failed) error
    """
    _now = now or _time.time

    # Auto-convert dict to WorkflowDefinition
    if isinstance(definition, dict):
        from .types import workflow_from_dict
        definition = workflow_from_dict(definition)

    # Validate
    validation = validate_workflow_definition(_def_to_dict(definition))
    if not validation.valid:
        first = validation.issues[0]
        return WorkflowEvalResult(
            status="failed",
            error={"code": "VALIDATION_ERROR",
                   "message": f"{first.path}: {first.message}"},
        )

    guards = guards or WorkflowGuards()

    # Initialize scope: inputs, vars, and step bindings
    scope: TemplateScope = {
        "inputs": inputs or {},
        "vars": {},
    }

    state = {
        "iterations_used": 0,
        "started_at": _now(),
    }

    def _emit(ev_type, **kwargs):
        if on_event:
            on_event(WorkflowEvalEvent(type=ev_type, **kwargs))

    def _check_guards():
        if (guards.max_iterations is not None
                and state["iterations_used"] > guards.max_iterations):
            _emit("guard-exceeded", guard="max_iterations")
            raise _WorkflowTermination(
                "failed",
                error={
                    "code": "GUARD_EXCEEDED",
                    "message": (
                        f"max_iterations exceeded: "
                        f"{state['iterations_used']} > {guards.max_iterations}"
                    ),
                }
            )
        if (guards.deadline_seconds is not None
                and _now() - state["started_at"] > guards.deadline_seconds):
            _emit("guard-exceeded", guard="deadline_seconds")
            raise _WorkflowTermination(
                "failed",
                error={
                    "code": "GUARD_EXCEEDED",
                    "message": (
                        f"deadline_seconds ({guards.deadline_seconds}s) exceeded"
                    ),
                }
            )

    def _execute_steps(steps):
        """Execute a list of steps sequentially."""
        for step in steps:
            _check_guards()
            _emit("step-start", step_id=step.id, step_type=step.type)
            try:
                _execute_step(step)
                _emit("step-finish", step_id=step.id,
                      step_type=step.type, outcome="ok")
            except (_WorkflowTermination, _StepFailure):
                _emit("step-finish", step_id=step.id,
                      step_type=step.type, outcome="failed")
                raise

    def _execute_step(step):
        """Execute a single step, dispatching by type."""
        if step.type == "task":
            resolved = str(resolve_template(step.task, scope))
            result = run_task(step, resolved)
            result_dict = result.to_dict()
            scope[step.id] = result_dict
            if step.save_as:
                scope[step.save_as] = result_dict
            _emit("task-result", step_id=step.id, result=result)
            _check_guards()
            if result.error and result.status == "failed":
                raise _StepFailure(step.id, result.error)
            return

        elif step.type == "assert":
            if not evaluate_condition(step.condition, scope):
                msg = step.message or f"Assertion '{step.id}' failed"
                raise _WorkflowTermination(
                    "failed",
                    error={"code": "ASSERTION_FAILED", "message": msg}
                )
            return

        elif step.type == "if":
            if evaluate_condition(step.condition, scope):
                _execute_steps(step.then)
            elif step.else_:
                _execute_steps(step.else_)
            return

        elif step.type == "loop":
            step_cap = step.max_iterations
            local_iters = 0

            if step.count is not None:
                for _ in range(step.count):
                    local_iters += 1
                    state["iterations_used"] += 1
                    _check_guards()
                    if step_cap is not None and local_iters > step_cap:
                        return
                    _execute_steps(step.body)
            elif step.while_ is not None:
                while evaluate_condition(step.while_, scope):
                    local_iters += 1
                    state["iterations_used"] += 1
                    _check_guards()
                    if step_cap is not None and local_iters > step_cap:
                        return
                    _execute_steps(step.body)
            return

        elif step.type == "parallel":
            # Branches run concurrently via ThreadPoolExecutor.
            # Scope is shared; last write wins on conflicting save_as.
            def _run_branch(branch):
                _execute_steps(branch)

            with ThreadPoolExecutor(max_workers=len(step.branches)) as pool:
                futures = [pool.submit(_run_branch, b) for b in step.branches]
                for future in as_completed(futures):
                    # Re-raise any exception from a branch
                    future.result()
            return

        elif step.type == "retry":
            last_err = None
            for attempt in range(1, step.max_attempts + 1):
                try:
                    scope["vars"] = {
                        **(scope.get("vars") or {}), "attempt": attempt
                    }
                    _execute_steps(step.body)
                    return
                except _WorkflowTermination as err:
                    if err.status == "succeeded":
                        raise
                    last_err = err
                except _StepFailure as err:
                    last_err = err
            if isinstance(last_err, _WorkflowTermination):
                raise last_err
            raise _WorkflowTermination(
                "failed",
                error={
                    "code": "RETRY_EXHAUSTED",
                    "message": (
                        f"retry '{step.id}' failed after "
                        f"{step.max_attempts} attempts"
                    ),
                }
            )

        elif step.type == "human_approval":
            msg = None
            if step.message is not None:
                msg = str(resolve_template(step.message, scope))
            _emit("awaiting-approval", step_id=step.id, message=msg)
            approved = False
            if on_approval:
                approved = on_approval(step, msg)
            _emit("approval-decision", step_id=step.id, approved=approved)
            if not approved:
                raise _WorkflowTermination(
                    "failed",
                    error={
                        "code": "APPROVAL_REJECTED",
                        "message": f"Approval '{step.id}' was rejected"
                    }
                )
            return

        elif step.type == "wait_for":
            deadline = _now() + (step.timeout_ms / 1000.0)
            while _now() < deadline:
                _check_guards()
                if evaluate_condition(step.condition, scope):
                    return
                _time.sleep(step.poll_ms / 1000.0)
            raise _WorkflowTermination(
                "failed",
                error={
                    "code": "WAIT_FOR_TIMEOUT",
                    "message": (
                        f"wait_for '{step.id}' timed out after "
                        f"{step.timeout_ms}ms"
                    ),
                }
            )

        elif step.type == "succeed":
            output = None
            if step.output is not None:
                output = resolve_deep(step.output, scope)
            raise _WorkflowTermination("succeeded", output=output)

        elif step.type == "fail":
            msg = "Workflow failed"
            if step.message is not None:
                msg = str(resolve_template(step.message, scope))
            raise _WorkflowTermination(
                "failed",
                error={"code": "WORKFLOW_FAILED", "message": msg}
            )

    def _collect_bindings():
        """Collect bound step results, excluding inputs/vars."""
        return {
            k: v for k, v in scope.items()
            if k not in ("inputs", "vars")
        }

    # ── Top-level execution ─────────────────────────────────────────────
    try:
        _execute_steps(definition.steps)
        # Ran off the end: implicit success
        output = None
        if definition.output:
            output = resolve_deep(definition.output, scope)
        return WorkflowEvalResult(
            status="succeeded",
            output=output,
            iterations_used=state["iterations_used"],
            bindings=_collect_bindings(),
        )
    except _WorkflowTermination as term:
        output = term.output
        if term.status == "succeeded" and output is None and definition.output:
            output = resolve_deep(definition.output, scope)
        return WorkflowEvalResult(
            status=term.status,
            output=output,
            error=term.error,
            iterations_used=state["iterations_used"],
            bindings=_collect_bindings(),
        )
    except _StepFailure as sf:
        return WorkflowEvalResult(
            status="failed",
            error={
                "code": "STEP_FAILED",
                "message": f"Step '{sf.step_id}': {sf.message}"
            },
            iterations_used=state["iterations_used"],
            bindings=_collect_bindings(),
        )


def _def_to_dict(definition):
    """Convert a WorkflowDefinition to a plain dict for validation."""
    return {
        "steps": [_step_to_dict(s) for s in definition.steps],
        "output": definition.output,
        **definition._extra,
    }


def _step_to_dict(step):
    """Convert a typed step to a plain dict."""
    d = {"id": step.id, "type": step.type}

    if step.type == "task":
        d["task"] = step.task
        if step.save_as:
            d["save_as"] = step.save_as
        if step.timeout_seconds:
            d["timeout_seconds"] = step.timeout_seconds
    elif step.type == "assert":
        if step.condition:
            d["condition"] = step.condition.to_dict()
        if step.message:
            d["message"] = step.message
    elif step.type == "if":
        if step.condition:
            d["condition"] = step.condition.to_dict()
        d["then"] = [_step_to_dict(s) for s in step.then]
        if step.else_:
            d["else"] = [_step_to_dict(s) for s in step.else_]
    elif step.type == "loop":
        if step.count is not None:
            d["count"] = step.count
        if step.while_ is not None:
            d["while"] = step.while_.to_dict()
        d["body"] = [_step_to_dict(s) for s in step.body]
        if step.max_iterations is not None:
            d["max_iterations"] = step.max_iterations
    elif step.type == "parallel":
        d["branches"] = [
            [_step_to_dict(s) for s in b] for b in step.branches
        ]
    elif step.type == "human_approval":
        if step.message:
            d["message"] = step.message
        if step.timeout_seconds:
            d["timeout_seconds"] = step.timeout_seconds
    elif step.type == "retry":
        d["max_attempts"] = step.max_attempts
        d["body"] = [_step_to_dict(s) for s in step.body]
    elif step.type == "wait_for":
        if step.condition:
            d["condition"] = step.condition.to_dict()
        d["timeout_ms"] = step.timeout_ms
        d["poll_ms"] = step.poll_ms
    elif step.type == "succeed":
        if step.output:
            d["output"] = step.output
    elif step.type == "fail":
        if step.message:
            d["message"] = step.message

    d.update(step._extra)
    return d
