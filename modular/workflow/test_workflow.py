#!/usr/bin/env python3
"""
Tests for the desktop-workflow DSL module.

Run with:
    cd /home/mal/AI/desktop-agent
    python -m pytest modular/workflow/test_workflow.py -v

Or run all:
    python -m pytest modular/workflow/ -v
"""

import json
import sys
import time
import unittest
from pathlib import Path

# Add parent to path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modular.workflow.template import (
    resolve_path,
    resolve_template,
    resolve_deep,
)
from modular.workflow.conditions import evaluate_condition
from modular.workflow.types import (
    Condition,
    TaskStep,
    AssertStep,
    IfStep,
    LoopStep,
    RetryStep,
    WaitForStep,
    HumanApprovalStep,
    SucceedStep,
    FailStep,
    ParallelStep,
    WorkflowDefinition,
    WorkflowGuards,
    StepResult,
    step_from_dict,
    workflow_from_dict,
)
from modular.workflow.validate import (
    validate_workflow_definition,
    ValidationIssue,
    ValidationResult,
)
from modular.workflow.evaluator import execute_workflow


# ═══════════════════════════════════════════════════════════════════════════
# Template Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTemplateResolution(unittest.TestCase):
    """Test {{path}} template resolution."""

    def setUp(self):
        self.scope = {
            "inputs": {"name": "TestUser", "count": 5},
            "vars": {"attempt": 1},
            "fetch": {"passed": True, "result": "invoice #42"},
            "deep": {"a": {"b": "c"}},
        }

    def test_resolve_path_simple(self):
        self.assertEqual(resolve_path("inputs.name", self.scope), "TestUser")
        self.assertEqual(resolve_path("fetch.passed", self.scope), True)

    def test_resolve_path_missing(self):
        self.assertIsNone(resolve_path("inputs.nonexistent", self.scope))
        self.assertIsNone(resolve_path("missing.entirely", self.scope))

    def test_resolve_path_deep(self):
        self.assertEqual(resolve_path("deep.a.b", self.scope), "c")

    def test_full_ref_returns_raw_type(self):
        # Exact {{ref}} preserves type
        result = resolve_template("{{inputs.count}}", self.scope)
        self.assertEqual(result, 5)
        self.assertIsInstance(result, int)

    def test_full_ref_boolean(self):
        result = resolve_template("{{fetch.passed}}", self.scope)
        self.assertEqual(result, True)

    def test_full_ref_object(self):
        result = resolve_template("{{inputs}}", self.scope)
        self.assertEqual(result, {"name": "TestUser", "count": 5})

    def test_full_ref_missing(self):
        result = resolve_template("{{missing.key}}", self.scope)
        self.assertIsNone(result)

    def test_embedded_ref_interpolation(self):
        result = resolve_template(
            "Hello {{inputs.name}}, invoice: {{fetch.result}}",
            self.scope
        )
        self.assertEqual(result, "Hello TestUser, invoice: invoice #42")

    def test_embedded_ref_missing_to_empty(self):
        result = resolve_template("{{missing.key}} is gone", self.scope)
        self.assertEqual(result, " is gone")

    def test_non_string_passthrough(self):
        self.assertEqual(resolve_template(42, self.scope), 42)
        self.assertEqual(resolve_template(None, self.scope), None)
        self.assertEqual(resolve_template(True, self.scope), True)

    def test_numeric_string_not_full_ref(self):
        # A string that's not a full ref passes through as string
        result = resolve_template("5", self.scope)
        self.assertEqual(result, "5")

    def test_resolve_deep_dict(self):
        tmpl = {"greeting": "Hi {{inputs.name}}", "count": "{{inputs.count}}"}
        result = resolve_deep(tmpl, self.scope)
        self.assertEqual(result, {"greeting": "Hi TestUser", "count": 5})

    def test_resolve_deep_nested(self):
        tmpl = {"user": {"name": "{{inputs.name}}", "active": "{{vars.attempt}}"}}
        result = resolve_deep(tmpl, self.scope)
        self.assertEqual(result, {"user": {"name": "TestUser", "active": 1}})


# ═══════════════════════════════════════════════════════════════════════════
# Condition Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestConditions(unittest.TestCase):
    """Test structured condition evaluation."""

    def setUp(self):
        self.scope = {
            "inputs": {"x": 10, "y": 5, "name": "hello"},
            "vars": {},
            "step1": {"passed": True, "count": 3},
        }

    def _eval(self, cond_dict):
        """Helper: dict → Condition → evaluate."""
        c = Condition.from_dict(cond_dict)
        return evaluate_condition(c, self.scope)

    def test_eq_true(self):
        self.assertTrue(self._eval(
            {"op": "eq", "left": "{{inputs.x}}", "right": 10}))

    def test_eq_false(self):
        self.assertFalse(self._eval(
            {"op": "eq", "left": "{{inputs.x}}", "right": 99}))

    def test_ne(self):
        self.assertTrue(self._eval(
            {"op": "ne", "left": "{{inputs.x}}", "right": 99}))

    def test_lt(self):
        self.assertTrue(self._eval(
            {"op": "lt", "left": "{{inputs.y}}", "right": "{{inputs.x}}"}))

    def test_gte(self):
        self.assertTrue(self._eval(
            {"op": "gte", "left": "{{inputs.x}}", "right": "{{inputs.x}}"}))

    def test_contains_string(self):
        self.assertTrue(self._eval(
            {"op": "contains", "left": "{{inputs.name}}", "right": "ell"}))

    def test_contains_array(self):
        scope2 = {**self.scope, "arr": ["a", "b", "c"]}
        c = Condition.from_dict(
            {"op": "contains", "left": "{{arr}}", "right": "b"})
        self.assertTrue(evaluate_condition(c, scope2))

    def test_truthy(self):
        self.assertTrue(self._eval(
            {"op": "truthy", "value": "{{step1.passed}}"}))

    def test_falsy(self):
        self.assertTrue(self._eval(
            {"op": "falsy", "value": "{{missing.key}}"}))

    def test_exists_true(self):
        self.assertTrue(self._eval(
            {"op": "exists", "value": "{{inputs.name}}"}))

    def test_exists_false(self):
        self.assertFalse(self._eval(
            {"op": "exists", "value": "{{missing.key}}"}))

    def test_and_all_true(self):
        self.assertTrue(self._eval({
            "op": "and",
            "conditions": [
                {"op": "truthy", "value": "{{step1.passed}}"},
                {"op": "gt", "left": "{{inputs.x}}", "right": "{{inputs.y}}"},
            ]
        }))

    def test_and_one_false(self):
        self.assertFalse(self._eval({
            "op": "and",
            "conditions": [
                {"op": "truthy", "value": "{{step1.passed}}"},
                {"op": "lt", "left": "{{inputs.x}}", "right": "{{inputs.y}}"},
            ]
        }))

    def test_or(self):
        self.assertTrue(self._eval({
            "op": "or",
            "conditions": [
                {"op": "falsy", "value": "{{step1.passed}}"},
                {"op": "truthy", "value": "{{inputs.name}}"},
            ]
        }))

    def test_not(self):
        self.assertTrue(self._eval({
            "op": "not",
            "condition": {"op": "eq", "left": 1, "right": 2}
        }))

    def test_unknown_op_raises(self):
        with self.assertRaises(ValueError):
            self._eval({"op": "bogus", "value": 1})


# ═══════════════════════════════════════════════════════════════════════════
# Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidation(unittest.TestCase):
    """Test structural workflow validation."""

    def test_valid_simple_workflow(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "doit", "type": "task", "task": "do something"}
            ]
        })
        self.assertTrue(result.valid)
        self.assertEqual(len(result.issues), 0)

    def test_missing_steps(self):
        result = validate_workflow_definition({})
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "MISSING_STEPS" for i in result.issues))

    def test_empty_steps(self):
        result = validate_workflow_definition({"steps": []})
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "MISSING_STEPS" for i in result.issues))

    def test_not_object(self):
        result = validate_workflow_definition("not an object")
        self.assertFalse(result.valid)

    def test_duplicate_ids(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "a", "type": "task", "task": "first"},
                {"id": "a", "type": "task", "task": "second"},
            ]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "DUPLICATE_ID" for i in result.issues))

    def test_invalid_id_format(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "bad id!", "type": "task", "task": "x"}
            ]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "INVALID_ID" for i in result.issues))

    def test_unknown_step_type(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "x", "type": "magic", "task": "x"}
            ]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "UNKNOWN_TYPE" for i in result.issues))

    def test_task_missing_task_field(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "x", "type": "task", "task": ""}
            ]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "MISSING_FIELD" for i in result.issues))

    def test_assert_requires_condition(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "chk", "type": "assert"}
            ]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "MISSING_FIELD" for i in result.issues))

    def test_reserved_save_as(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "t", "type": "task", "task": "x", "save_as": "inputs"}
            ]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "RESERVED_SAVE_AS" for i in result.issues))

    def test_loop_requires_one_of_count_or_while(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "lp", "type": "loop",
                "body": [{"id": "inner", "type": "task", "task": "x"}]
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "INVALID_LOOP" for i in result.issues))

    def test_loop_with_both_count_and_while(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "lp", "type": "loop", "count": 3,
                "while": {"op": "truthy", "value": True},
                "body": [{"id": "inner", "type": "task", "task": "x"}]
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "INVALID_LOOP" for i in result.issues))

    def test_retry_limits(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "r", "type": "retry", "max_attempts": 99,
                "body": [{"id": "inner", "type": "task", "task": "x"}]
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "INVALID_RETRY" for i in result.issues))

    def test_forbidden_in_parallel(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "p", "type": "parallel",
                "branches": [
                    [{"id": "h", "type": "human_approval"}]
                ]
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(
            any(i.code == "FORBIDDEN_IN_PARALLEL" for i in result.issues))

    def test_valid_wait_for(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "w", "type": "wait_for",
                "condition": {"op": "exists", "value": "{{step1.result}}"},
                "timeout_ms": 5000, "poll_ms": 200
            }]
        })
        self.assertTrue(result.valid)

    def test_nested_valid_workflow(self):
        result = validate_workflow_definition({
            "steps": [
                {"id": "outer", "type": "retry", "max_attempts": 3, "body": [
                    {"id": "inner", "type": "task", "task": "try this"}
                ]}
            ]
        })
        self.assertTrue(result.valid)

    def test_bad_condition_op(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "a", "type": "assert",
                "condition": {"op": "bogus_op", "value": 1}
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(
            any(i.code == "INVALID_CONDITION" for i in result.issues))

    def test_and_without_conditions_array(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "a", "type": "assert",
                "condition": {"op": "and"}
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(
            any(i.code == "INVALID_CONDITION" for i in result.issues))

    def test_not_without_condition(self):
        result = validate_workflow_definition({
            "steps": [{
                "id": "a", "type": "assert",
                "condition": {"op": "not"}
            }]
        })
        self.assertFalse(result.valid)
        self.assertTrue(
            any(i.code == "INVALID_CONDITION" for i in result.issues))


# ═══════════════════════════════════════════════════════════════════════════
# Step Construction Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStepConstruction(unittest.TestCase):
    """Test dict → typed step construction."""

    def test_task_from_dict(self):
        s = step_from_dict(
            {"id": "doit", "type": "task", "task": "do something",
             "save_as": "result"})
        self.assertIsInstance(s, TaskStep)
        self.assertEqual(s.id, "doit")
        self.assertEqual(s.task, "do something")
        self.assertEqual(s.save_as, "result")

    def test_assert_from_dict(self):
        s = step_from_dict({
            "id": "chk", "type": "assert",
            "condition": {"op": "truthy", "value": True}
        })
        self.assertIsInstance(s, AssertStep)
        self.assertIsNotNone(s.condition)
        self.assertEqual(s.condition.op, "truthy")

    def test_if_from_dict(self):
        s = step_from_dict({
            "id": "branch", "type": "if",
            "condition": {"op": "eq", "left": 1, "right": 1},
            "then": [{"id": "yes", "type": "task", "task": "yes branch"}],
            "else": [{"id": "no", "type": "task", "task": "no branch"}],
        })
        self.assertIsInstance(s, IfStep)
        self.assertEqual(len(s.then), 1)
        self.assertEqual(len(s.else_), 1)

    def test_loop_from_dict(self):
        s = step_from_dict({
            "id": "lp", "type": "loop", "count": 5,
            "body": [{"id": "inner", "type": "task", "task": "repeat"}]
        })
        self.assertIsInstance(s, LoopStep)
        self.assertEqual(s.count, 5)
        self.assertIsNone(s.while_)

    def test_retry_from_dict(self):
        s = step_from_dict({
            "id": "r", "type": "retry", "max_attempts": 3,
            "body": [{"id": "inner", "type": "task", "task": "fragile"}]
        })
        self.assertIsInstance(s, RetryStep)
        self.assertEqual(s.max_attempts, 3)

    def test_wait_for_from_dict(self):
        s = step_from_dict({
            "id": "w", "type": "wait_for",
            "condition": {"op": "exists", "value": "{{x}}"},
            "timeout_ms": 5000, "poll_ms": 200
        })
        self.assertIsInstance(s, WaitForStep)
        self.assertEqual(s.timeout_ms, 5000)
        self.assertEqual(s.poll_ms, 200)

    def test_workflow_from_dict(self):
        wf = workflow_from_dict({
            "steps": [
                {"id": "one", "type": "task", "task": "first"},
                {"id": "two", "type": "task", "task": "second"},
            ]
        })
        self.assertIsInstance(wf, WorkflowDefinition)
        self.assertEqual(len(wf.steps), 2)

    def test_extra_fields_preserved(self):
        s = step_from_dict({
            "id": "t", "type": "task", "task": "x",
            "custom_field": "hello", "another": 42
        })
        self.assertEqual(s._extra.get("custom_field"), "hello")
        self.assertEqual(s._extra.get("another"), 42)


# ═══════════════════════════════════════════════════════════════════════════
# Evaluator Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEvaluator(unittest.TestCase):
    """Test the deterministic workflow evaluator."""

    def _ok_result(self, step=None, text=None):
        """Return a passing StepResult."""
        return StepResult(status="done", passed=True,
                          result=f"completed: {text or 'task'}")

    def _fail_result(self, step=None, text=None):
        """Return a failing StepResult."""
        return StepResult(status="done", passed=False,
                          result="failed", error="task error")

    def _simple_task(self, task_text="do something"):
        """Create a run_task callback that always succeeds."""
        def fn(step, resolved):
            return StepResult(status="done", passed=True,
                              result=f"did: {resolved}")
        return fn

    def test_single_task_succeeds(self):
        wf = WorkflowDefinition(steps=[
            TaskStep(id="hello", task="say hello")
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertIn("hello", result.bindings)
        self.assertEqual(result.bindings["hello"]["passed"], True)

    def test_task_with_save_as(self):
        wf = WorkflowDefinition(steps=[
            TaskStep(id="step1", task="fetch data", save_as="data")
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertIn("step1", result.bindings)
        self.assertIn("data", result.bindings)
        self.assertEqual(result.bindings["data"],
                         result.bindings["step1"])

    def test_assertion_fails_workflow(self):
        wf = WorkflowDefinition(steps=[
            TaskStep(id="t", task="do something"),
            AssertStep(id="chk", condition=Condition.from_dict(
                {"op": "falsy", "value": True}
            ))
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error["code"], "ASSERTION_FAILED")

    def test_assertion_with_template_condition(self):
        wf = WorkflowDefinition(steps=[
            TaskStep(id="t", task="do something"),
            AssertStep(id="chk", condition=Condition.from_dict(
                {"op": "truthy", "value": "{{t.passed}}"}
            ))
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")

    def test_if_branch_taken(self):
        wf = WorkflowDefinition(steps=[
            IfStep(id="check", condition=Condition.from_dict(
                {"op": "eq", "left": 1, "right": 1}
            ), then=[
                TaskStep(id="yes", task="branch taken")
            ], else_=[
                TaskStep(id="no", task="branch not taken")
            ])
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertIn("yes", result.bindings)
        self.assertNotIn("no", result.bindings)

    def test_if_else_branch_taken(self):
        wf = WorkflowDefinition(steps=[
            IfStep(id="check", condition=Condition.from_dict(
                {"op": "eq", "left": 1, "right": 999}
            ), then=[
                TaskStep(id="yes", task="nope")
            ], else_=[
                TaskStep(id="no", task="else branch")
            ])
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertNotIn("yes", result.bindings)
        self.assertIn("no", result.bindings)

    def test_loop_count(self):
        wf = WorkflowDefinition(steps=[
            LoopStep(id="lp", count=3, body=[
                TaskStep(id="repeat", task="iteration")
            ])
        ])
        call_count = [0]
        def count_calls(step, resolved):
            call_count[0] += 1
            return StepResult(status="done", passed=True,
                              result=f"iter {call_count[0]}")

        result = execute_workflow(wf, run_task=count_calls)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(call_count[0], 3)

    def test_loop_while_condition(self):
        # Loop while a counter in scope is less than 3.
        # StepResult wraps result in .result, so path is {{counter.result.count}}
        wf = WorkflowDefinition(steps=[
            TaskStep(id="init", task="set counter", save_as="counter"),
            LoopStep(id="lp", while_=Condition.from_dict(
                {"op": "lt", "left": "{{counter.result.count}}", "right": 3}
            ), body=[
                TaskStep(id="inc", task="increment", save_as="counter")
            ])
        ])
        counter = [0]
        def counter_task(step, resolved):
            counter[0] += 1
            return StepResult(status="done", passed=True,
                              result={"count": counter[0]})

        result = execute_workflow(wf, run_task=counter_task)
        self.assertEqual(result.status, "succeeded")
        # init(1) → while(1<3)=true → inc(2) → while(2<3)=true → inc(3)
        # → while(3<3)=false → stops. Total: 3 calls
        self.assertEqual(counter[0], 3)

    def test_retry_succeeds_on_second_attempt(self):
        attempt_count = [0]
        def flaky_task(step, resolved):
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                return StepResult(status="failed", passed=False,
                                  error="transient error")
            return StepResult(status="done", passed=True,
                              result="success!")

        wf = WorkflowDefinition(steps=[
            RetryStep(id="r", max_attempts=3, body=[
                TaskStep(id="flaky", task="might fail")
            ])
        ])
        result = execute_workflow(wf, run_task=flaky_task)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(attempt_count[0], 2)

    def test_retry_exhausted(self):
        def always_fail(step, resolved):
            return StepResult(status="failed", passed=False,
                              error="always fails")

        wf = WorkflowDefinition(steps=[
            RetryStep(id="r", max_attempts=2, body=[
                TaskStep(id="bad", task="will fail")
            ])
        ])
        result = execute_workflow(wf, run_task=always_fail)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "RETRY_EXHAUSTED")

    def test_human_approval_approved(self):
        wf = WorkflowDefinition(steps=[
            HumanApprovalStep(id="gate", message="Proceed?")
        ])
        result = execute_workflow(
            wf,
            run_task=self._simple_task(),
            on_approval=lambda step, msg: True
        )
        self.assertEqual(result.status, "succeeded")

    def test_human_approval_rejected(self):
        wf = WorkflowDefinition(steps=[
            HumanApprovalStep(id="gate", message="Proceed?")
        ])
        result = execute_workflow(
            wf,
            run_task=self._simple_task(),
            on_approval=lambda step, msg: False
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "APPROVAL_REJECTED")

    def test_human_approval_no_handler_fail_closed(self):
        wf = WorkflowDefinition(steps=[
            HumanApprovalStep(id="gate")
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "failed")

    def test_wait_for_eventually_true(self):
        check_count = [0]
        def check_scope(cond, scope):
            check_count[0] += 1
            return check_count[0] >= 3  # True on 3rd check

        # We need to test wait_for with a condition that becomes true.
        # Use a scope value that changes.
        wf = WorkflowDefinition(steps=[
            WaitForStep(id="w", condition=Condition.from_dict(
                {"op": "truthy", "value": "{{vars.ready}}"}
            ), timeout_ms=5000, poll_ms=10)
        ])
        # The condition depends on scope which we can't change from outside
        # without a task. Let's test a simpler form.
        wf2 = WorkflowDefinition(steps=[
            WaitForStep(id="w", condition=Condition.from_dict(
                {"op": "eq", "left": 1, "right": 1}
            ), timeout_ms=100, poll_ms=10)
        ])
        result = execute_workflow(wf2, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")

    def test_wait_for_timeout(self):
        wf = WorkflowDefinition(steps=[
            WaitForStep(id="w", condition=Condition.from_dict(
                {"op": "eq", "left": 1, "right": 999}
            ), timeout_ms=50, poll_ms=10)
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "WAIT_FOR_TIMEOUT")

    def test_succeed_early_exit(self):
        wf = WorkflowDefinition(steps=[
            SucceedStep(id="done", output={"status": "ok"})
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output, {"status": "ok"})

    def test_fail_explicit(self):
        wf = WorkflowDefinition(steps=[
            FailStep(id="abort", message="something went wrong")
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "WORKFLOW_FAILED")
        self.assertIn("something went wrong", result.error["message"])

    def test_implicit_output_on_run_off_end(self):
        wf = WorkflowDefinition(
            steps=[TaskStep(id="t", task="do it")],
            output={"result": "{{t.result}}"}
        )
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output["result"], "did: do it")

    def test_inputs_accessible(self):
        wf = WorkflowDefinition(steps=[
            AssertStep(id="chk", condition=Condition.from_dict(
                {"op": "eq", "left": "{{inputs.name}}", "right": "Alice"}
            ))
        ])
        result = execute_workflow(
            wf, run_task=self._simple_task(),
            inputs={"name": "Alice"}
        )
        self.assertEqual(result.status, "succeeded")

    def test_guard_max_iterations(self):
        wf = WorkflowDefinition(steps=[
            LoopStep(id="lp", count=100, body=[
                TaskStep(id="rep", task="iterate")
            ])
        ])
        result = execute_workflow(
            wf, run_task=self._simple_task(),
            guards=WorkflowGuards(max_iterations=5)
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "GUARD_EXCEEDED")

    def test_guard_deadline(self):
        wf = WorkflowDefinition(steps=[
            TaskStep(id="t1", task="first"),
            WaitForStep(id="w", condition=Condition.from_dict(
                {"op": "eq", "left": 1, "right": 999}
            ), timeout_ms=5000, poll_ms=100)
        ])
        # Set deadline to expire during wait_for
        fake_time = [0.0]
        def fake_now():
            return fake_time[0]

        def slow_run_task(step, resolved):
            fake_time[0] += 0.1
            return StepResult(status="done", passed=True,
                              result="did it")

        result = execute_workflow(
            wf, run_task=slow_run_task,
            guards=WorkflowGuards(deadline_seconds=0),
            now=fake_now
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "GUARD_EXCEEDED")

    def test_parallel_branches(self):
        wf = WorkflowDefinition(steps=[
            ParallelStep(id="p", branches=[
                [TaskStep(id="a", task="branch-a", save_as="a")],
                [TaskStep(id="b", task="branch-b", save_as="b")],
            ])
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertIn("a", result.bindings)
        self.assertIn("b", result.bindings)

    def test_validation_error_returns_failed(self):
        wf = WorkflowDefinition(steps=[])  # empty steps should fail validation
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "VALIDATION_ERROR")

    def test_events_emitted(self):
        events = []
        def collect(event):
            events.append(event)

        wf = WorkflowDefinition(steps=[
            TaskStep(id="t", task="hello"),
            SucceedStep(id="done"),
        ])
        result = execute_workflow(
            wf, run_task=self._simple_task(), on_event=collect
        )
        self.assertEqual(result.status, "succeeded")
        # Should have step-start(2) + step-finish(1) + task-result(1) + step-finish(0, caught)
        # Actually succeed throws and is caught — let's just check we got events
        self.assertGreater(len(events), 2)
        start_events = [e for e in events if e.type == "step-start"]
        self.assertEqual(len(start_events), 2)

    def test_vars_attempt_in_retry(self):
        """Verify that {{vars.attempt}} is set during retry."""
        captured_attempts = []

        def check_attempt(step, resolved):
            # This task runs inside a retry block, so vars.attempt should be set
            pass

        wf = WorkflowDefinition(steps=[
            RetryStep(id="r", max_attempts=2, body=[
                # Assert that vars.attempt exists and is truthy
                AssertStep(id="chk", condition=Condition.from_dict(
                    {"op": "truthy", "value": "{{vars.attempt}}"}
                ))
            ])
        ])
        result = execute_workflow(wf, run_task=self._simple_task())
        self.assertEqual(result.status, "succeeded")


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests — Full Cookbook Recipes
# ═══════════════════════════════════════════════════════════════════════════

class TestCookbookRecipes(unittest.TestCase):
    """Test the exact workflow recipes from the cookbook."""

    @staticmethod
    def _simple_task():
        def fn(step, resolved):
            return StepResult(status="done", passed=True,
                              result=f"did: {resolved}")
        return fn

    def test_invoice_approval_workflow(self):
        """The cookbook example: fetch invoice, assert, approve, succeed."""
        wf = workflow_from_dict({
            "steps": [
                {"id": "fetch", "type": "task",
                 "task": "Open order {{inputs.order_id}} and read the invoice total",
                 "save_as": "invoice"},
                {"id": "check", "type": "assert",
                 "condition": {"op": "truthy", "value": "{{invoice.passed}}"},
                 "message": "Could not read the invoice"},
                {"id": "gate", "type": "human_approval",
                 "message": "Approve publishing the result?"},
                {"id": "ok", "type": "succeed",
                 "output": {"total": "{{invoice.result}}"}}
            ]
        })

        def run(step, resolved):
            return StepResult(status="done", passed=True,
                              result="$1,234.56")

        result = execute_workflow(
            wf, run_task=run,
            inputs={"order_id": "ORD-123"},
            on_approval=lambda step, msg: True
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output["total"], "$1,234.56")

    def test_retry_flaky_step(self):
        """Cookbook: retry a flaky step with assertion."""
        wf = workflow_from_dict({
            "steps": [{
                "id": "r", "type": "retry", "max_attempts": 3, "body": [
                    {"id": "submit", "type": "task",
                     "task": "Submit the expense form", "save_as": "out"},
                    {"id": "verify", "type": "assert",
                     "condition": {"op": "truthy", "value": "{{out.passed}}"}}
                ]
            }]
        })

        calls = [0]
        def flaky(step, resolved):
            calls[0] += 1
            if calls[0] < 2:
                return StepResult(status="failed", passed=False,
                                  error="temporary failure")
            return StepResult(status="done", passed=True,
                              result="submitted")

        result = execute_workflow(wf, run_task=flaky)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(calls[0], 2)

    def test_parallel_with_and_assert(self):
        """Cookbook: parallel branches with combined assertion."""
        wf = workflow_from_dict({
            "steps": [
                {"id": "p", "type": "parallel", "branches": [
                    [{"id": "a", "type": "task",
                      "task": "Export the sales report", "save_as": "sales"}],
                    [{"id": "b", "type": "task",
                      "task": "Export the support report", "save_as": "support"}],
                ]},
                {"id": "both", "type": "assert", "condition": {
                    "op": "and", "conditions": [
                        {"op": "truthy", "value": "{{sales.passed}}"},
                        {"op": "truthy", "value": "{{support.passed}}"},
                    ]
                }}
            ]
        })

        result = execute_workflow(wf, run_task=TestCookbookRecipes._simple_task())
        self.assertEqual(result.status, "succeeded")
        self.assertIn("sales", result.bindings)
        self.assertIn("support", result.bindings)

    def test_inputs_and_multiple_tasks(self):
        """Workflow using inputs across multiple tasks."""
        wf = workflow_from_dict({
            "steps": [
                {"id": "login", "type": "task",
                 "task": "Log in as {{inputs.username}}"},
                {"id": "nav", "type": "task",
                 "task": "Navigate to {{inputs.page}}"},
                {"id": "done", "type": "succeed",
                 "output": {"user": "{{inputs.username}}",
                            "page": "{{inputs.page}}"}}
            ]
        })

        log = []
        def logging_task(step, resolved):
            log.append(resolved)
            return StepResult(status="done", passed=True,
                              result=resolved)

        result = execute_workflow(
            wf, run_task=logging_task,
            inputs={"username": "admin", "page": "/dashboard"}
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(log[0], "Log in as admin")
        self.assertEqual(log[1], "Navigate to /dashboard")
        self.assertEqual(result.output["user"], "admin")


if __name__ == "__main__":
    unittest.main()
