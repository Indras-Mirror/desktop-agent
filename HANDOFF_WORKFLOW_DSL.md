# Handoff: Workflow DSL + Vision Fallback for desktop-agent

**Branch:** `workflow-dsl` (based on `experimental-analyze-v2`)
**Commit:** `65ca74b`
**Date:** 2026-06-16
**Author:** Claude Opus 4.6

---

## Table of Contents

1. [What Was Built](#1-what-was-built)
2. [File Inventory](#2-file-inventory)
3. [Architecture Deep Dive](#3-architecture-deep-dive)
4. [How to Test](#4-how-to-test)
5. [How to Use](#5-how-to-use)
6. [What's Done vs. What's Next](#6-whats-done-vs-whats-next)
7. [Design Decisions & Tradeoffs](#7-design-decisions--tradeoffs)
8. [Known Issues & Limitations](#8-known-issues--limitations)
9. [Rollback Plan](#9-rollback-plan)
10. [OpenRouter Credential Info](#10-openrouter-credential-info)
11. [Source Material](#11-source-material)

---

## 1. What Was Built

Two independent but complementary capabilities for `desktop-agent`:

### 1A. Workflow DSL — Deterministic Task Composition Engine

Ported from [open-cowork](https://github.com/coasty-ai/open-cowork)'s workflow DSL (TypeScript → Python), adapted for local-first desktop automation. The DSL lets you compose desktop-agent commands into structured, recoverable, approvable sequences.

**10 Step Types:**
| Step | Purpose | JSON Example |
|------|---------|-------------|
| `task` | Execute a desktop-agent command | `{"id":"x","type":"task","task":"Click Save","save_as":"result"}` |
| `assert` | Fail if condition is false | `{"id":"x","type":"assert","condition":{"op":"truthy","value":"{{result.passed}}"}}` |
| `if` | Branch on condition | `{"id":"x","type":"if","condition":{...},"then":[...],"else":[...]}` |
| `loop` | Repeat N times or while condition | `{"id":"x","type":"loop","count":3,"body":[...]}` |
| `parallel` | Concurrent branches | `{"id":"x","type":"parallel","branches":[[...],[...]]}` |
| `retry` | Retry body on failure | `{"id":"x","type":"retry","max_attempts":3,"body":[...]}` |
| `human_approval` | Pause for human decision | `{"id":"x","type":"human_approval","message":"Proceed?"}` |
| `wait_for` | Poll screen until condition met | `{"id":"x","type":"wait_for","condition":{...},"timeout_ms":5000}` |
| `succeed` | Explicit early success | `{"id":"x","type":"succeed","output":{"key":"value"}}` |
| `fail` | Explicit early failure | `{"id":"x","type":"fail","message":"Something went wrong"}` |

**13 Condition Ops (injection-safe — no `eval()`/`exec()`):**
`eq`, `ne`, `lt`, `gt`, `lte`, `gte`, `contains`, `truthy`, `falsy`, `exists`, `and`, `or`, `not`

### 1B. Vision Fallback — OpenRouter/Grok Screen Understanding

When AT-SPI + RapidOCR produce poor results (Firefox, Electron apps, games), desktop-agent can send a screenshot to a vision model for natural language description. Uses the same OpenRouter credentials as the existing `visionproxy` MCP server.

**Default model:** `x-ai/grok-4.3`
**Fallback chain:** `gpt-4o` → `claude-sonnet-4-20250514`
**Cost:** ~$0.002 per description (Grok 4.3 vision pricing)

### 1C. CLI Integration

Three new CLI commands wired into `modular/cli.py`:
- `desktop-agent vision` — AI-powered screen description
- `desktop-agent workflow validate <file.json>` — validate workflow definitions
- `desktop-agent workflow run <file.json>` — dry-run or live execution

---

## 2. File Inventory

### New Files (7 created)

```
modular/workflow/__init__.py       # Module exports — all public API surface
modular/workflow/types.py          # 10 step dataclasses, 13 condition ops, JSON↔typed conversion
modular/workflow/template.py       # {{path}} dotted template resolver (~60 lines)
modular/workflow/conditions.py     # Structured condition evaluator (~90 lines, no eval)
modular/workflow/validate.py       # Structural validator (~230 lines)
modular/workflow/evaluator.py      # Deterministic interpreter (~270 lines, synchronous)
modular/workflow/test_workflow.py  # 85 unit tests (~970 lines)
modular/vision_fallback.py         # OpenRouter vision API client (~200 lines)
HANDOFF_WORKFLOW_DSL.md            # This file
```

### Modified Files (1)

```
modular/cli.py                     # Added vision + workflow commands, updated help text
```

### Unchanged Files

```
modular/analyze.py                 # No changes — workflow can call analyze as a task
modular/input.py                   # No changes — workflow can call click/type/etc. as tasks
modular/window.py                  # No changes
modular/ocr.py                     # No changes
modular/atspi.py                   # No changes
modular/config.py                  # No changes
modular/task_system.py             # No changes — existing task recording is separate system
```

---

## 3. Architecture Deep Dive

### 3A. Workflow DSL — From JSON to Execution

```
JSON definition (dict)
    │
    ▼
workflow_from_dict()          [types.py:237]
    │  Parses JSON → typed dataclasses (TaskStep, IfStep, etc.)
    │  Condition dicts → Condition objects (recursive)
    │
    ▼
validate_workflow_definition() [validate.py:259]
    │  Checks: ID format, uniqueness, nesting ≤8, steps ≤200,
    │  parallel branches ≤16, condition structure, forbidden-in-parallel,
    │  reserved names, retry bounds, loop count/while exclusivity,
    │  wait_for timeout/poll bounds
    │  Returns: ValidationResult(valid=bool, issues=List[Issue])
    │
    ▼
execute_workflow()             [evaluator.py:67]
    │  Re-validates (defense in depth)
    │  Initializes scope: {inputs: {...}, vars: {}}
    │  Executes steps sequentially via _execute_steps()
    │
    ├─► _execute_step(step)   [evaluator.py:134]
    │     Dispatches by step.type:
    │
    │     task:            run_task(step, resolved_text) → bind result to scope[step.id]
    │     assert:          evaluate_condition(step.condition, scope) → raise on false
    │     if:              evaluate_condition → execute then[] or else[]
    │     loop:            for count or while condition → execute body[]
    │     parallel:        ThreadPoolExecutor → execute branches concurrently
    │     retry:           try/except loop → retry body[] up to max_attempts
    │     human_approval:  on_approval(step, msg) → raise on reject
    │     wait_for:        poll condition every poll_ms until timeout_ms
    │     succeed/fail:    raise _WorkflowTermination(status, output, error)
    │
    └─► Returns: WorkflowEvalResult(status, output, error, bindings, iterations)
```

### 3B. Injected Dependencies (the key pattern)

The evaluator has **zero side effects** — everything external is injected:

```python
execute_workflow(
    definition,          # WorkflowDefinition — the JSON-parsed DSL
    run_task,            # Callable[[TaskStep, str], StepResult] — executes commands
    inputs=None,         # Dict — workflow parameters ({{inputs.key}})
    guards=None,         # WorkflowGuards — max_iterations, deadline_seconds
    on_approval=None,    # Callable[[HumanApprovalStep, str?], bool] — human decision
    on_event=None,       # Callable[[WorkflowEvalEvent], None] — event stream
    now=None,            # Callable[[], float] — injectable clock
)
```

This means:
- **Testing:** Inject mock `run_task` that returns canned `StepResult` — no desktop needed
- **Dry-run vs. live:** Same evaluator, different `run_task` callback
- **Approval flow:** Inject CLI prompt, webhook, or auto-approve callback
- **Time travel:** Inject `now` to test deadline guards deterministically

### 3C. Template System

Template references use `{{dotted.path}}` syntax. The scope is a flat-ish dict:

```python
scope = {
    "inputs": {"name": "Alice", "page": "/dashboard"},  # workflow inputs
    "vars": {"attempt": 2},                               # runtime variables
    "step1": {"passed": True, "result": "invoice #42"},  # bound task result
    "data":  {"passed": True, "result": "...", ...},      # save_as alias
}
```

Resolution rules (mirror open-cowork's `template.ts` exactly):
1. **Exact `{{ref}}`** returns the raw value, preserving type (int, bool, dict, list)
2. **Embedded `text {{ref}} more`** interpolates each ref as string; missing → `""`; objects → JSON
3. **Non-strings** pass through unchanged
4. **Missing paths** → `None` (exact) or `""` (embedded)

Example:
```python
resolve_template("{{inputs.name}}", scope)           # → "Alice" (str)
resolve_template("{{step1.passed}}", scope)           # → True (bool)
resolve_template("Hi {{inputs.name}}!", scope)        # → "Hi Alice!"
resolve_template("Count: {{inputs.count}}", scope)    # → "Count: " (missing → "")
```

### 3D. Control Flow via Typed Exceptions

The evaluator uses two internal exception classes for clean stack unwinding:

```python
class _WorkflowTermination(Exception):  # succeed/fail/guard exceeded
    status: str      # "succeeded" | "failed"
    output: dict?    # succeed output payload
    error: dict?     # {code, message}

class _StepFailure(Exception):          # transport-level task failure
    step_id: str
    message: str
```

The top-level `try/except` in `execute_workflow()` catches both and converts them into `WorkflowEvalResult`. This avoids callback hell — any nested step can signal early termination and it unwinds cleanly.

### 3E. Vision Fallback Architecture

```
desktop-agent vision "Is there a Save button?"
    │
    ▼
describe_screen(image_path=None, prompt=question)
    │  If no image_path: auto-captures screenshot via input.screenshot()
    │  Saves to /tmp/desktop-agent-vision.png
    │
    ▼
describe_image(image_path, prompt, model="x-ai/grok-4.3")
    │  Reads image, base64-encodes
    │  POSTs to https://openrouter.ai/api/v1/chat/completions
    │  Headers: Authorization: Bearer $OPENROUTER_API_KEY
    │  Body: {model, messages: [{role:"user", content: [text, image_url]}]}
    │
    ├─ HTTP 200 → returns model response text
    ├─ HTTP error → tries next model in FALLBACK_MODELS list
    └─ All fail → raises RuntimeError
    │
    ▼
Returns: {success: bool, description: str, model: str, error: str}
```

**Credential source:** The `OPENROUTER_API_KEY` is read from environment. The `visionproxy` MCP server already has this key in its config at `/home/mal/.claude/local-settings.json`. When running desktop-agent from a context where that env var is set (e.g., via the visionproxy MCP server process), it works automatically. For standalone use, export it:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

---

## 4. How to Test

### 4A. Workflow Unit Tests (85 tests, 0.14s)

```bash
cd /home/mal/AI/desktop-agent
python -m pytest modular/workflow/test_workflow.py -v

# Test categories and counts:
#   TestTemplateResolution      13 tests — dotted paths, full/embedded refs, deep resolution
#   TestConditions              16 tests — all 13 ops, edge cases, unknown op
#   TestValidation              20 tests — IDs, limits, nesting, conditions, forbidden patterns
#   TestStepConstruction         7 tests — JSON→typed dataclasses, extra field preservation
#   TestEvaluator               22 tests — tasks, assertions, branching, loops, retry, guards
#   TestCookbookRecipes           4 tests — real recipes: approval gate, retry, parallel, inputs
```

All tests use injected `run_task` callbacks — no desktop interaction needed.

### 4B. Vision Fallback Smoke Test

```bash
cd /home/mal/AI/desktop-agent
OPENROUTER_API_KEY="sk-or-v1-..." python -c "
from modular.vision_fallback import describe_screen, is_available
print('Available:', is_available())
# This will make a real API call:
result = describe_screen('/tmp/desktop-agent/screenshot_*.png')
print(result['success'], result['model'], result['description'][:200])
"
```

### 4C. CLI Smoke Tests

```bash
# Validate a workflow
echo '{"steps":[{"id":"t","type":"task","task":"hello"}]}' > /tmp/test-wf.json
desktop-agent workflow validate /tmp/test-wf.json

# Dry-run a workflow
desktop-agent workflow run /tmp/test-wf.json

# Live run with approval (interactive)
desktop-agent workflow run --live /tmp/test-wf.json

# Vision (requires OPENROUTER_API_KEY in env)
desktop-agent vision "What applications are visible?"
```

### 4D. Test the Approval Flow

```bash
cat > /tmp/approval-test.json << 'EOF'
{
  "steps": [
    {"id": "doit", "type": "task", "task": "Simulated task", "save_as": "result"},
    {"id": "gate", "type": "human_approval", "message": "Approve continuing?"},
    {"id": "done", "type": "succeed", "output": {"outcome": "{{result.result}}"}
  ]
}
EOF

desktop-agent workflow run --live /tmp/approval-test.json
# You'll be prompted: "Approve? [y/N]:"
```

---

## 5. How to Use

### 5A. Workflow JSON Examples

**Simple task with assertion:**
```json
{
  "steps": [
    {"id": "open", "type": "task", "task": "Open Firefox", "save_as": "browser"},
    {"id": "check", "type": "assert",
     "condition": {"op": "truthy", "value": "{{browser.passed}}"},
     "message": "Browser didn't open"}
  ]
}
```

**Retry a flaky action:**
```json
{
  "steps": [{
    "id": "r", "type": "retry", "max_attempts": 3, "body": [
      {"id": "click-save", "type": "task", "task": "Click the Save button"},
      {"id": "verify", "type": "assert",
       "condition": {"op": "contains", "left": "{{click-save.result}}", "right": "saved"}}
    ]
  }]
}
```

**Parallel branches with combined assertion:**
```json
{
  "steps": [
    {"id": "parallel-fetch", "type": "parallel", "branches": [
      [{"id": "sales", "type": "task", "task": "Export sales report", "save_as": "sales"}],
      [{"id": "support", "type": "task", "task": "Export support report", "save_as": "support"}]
    ]},
    {"id": "check-both", "type": "assert", "condition": {
      "op": "and", "conditions": [
        {"op": "truthy", "value": "{{sales.passed}}"},
        {"op": "truthy", "value": "{{support.passed}}"}
      ]
    }}
  ]
}
```

**Loop with while condition:**
```json
{
  "steps": [
    {"id": "init", "type": "task", "task": "Get initial counter", "save_as": "state"},
    {"id": "poll", "type": "loop",
     "while": {"op": "lt", "left": "{{state.result.count}}", "right": 10},
     "body": [
       {"id": "tick", "type": "task", "task": "Wait and re-check", "save_as": "state"}
     ]
    }
  ]
}
```

**Full approval-gated workflow with inputs:**
```json
{
  "steps": [
    {"id": "open-jira", "type": "task",
     "task": "Open Firefox and navigate to https://jira.company.com",
     "save_as": "jira"},
    {"id": "check-loaded", "type": "assert",
     "condition": {"op": "exists", "value": "{{jira.result}}"},
     "message": "Jira didn't load"},
    {"id": "approval", "type": "human_approval",
     "message": "Create ticket titled '{{inputs.title}}' assigned to {{inputs.assignee}}?"},
    {"id": "create", "type": "task",
     "task": "Fill form with title {{inputs.title}}, assignee {{inputs.assignee}}, click Create",
     "save_as": "ticket"},
    {"id": "verify", "type": "assert",
     "condition": {"op": "contains", "left": "{{ticket.result}}", "right": "created"}},
    {"id": "done", "type": "succeed",
     "output": {"ticket": "{{ticket.result}}"}}
  ]
}
```

### 5B. Using the Vision Fallback

```bash
# Describe current screen
desktop-agent vision

# Ask a specific question
desktop-agent vision "Is there an error dialog visible?"

# JSON output (for programmatic use)
desktop-agent vision --json

# Different model
desktop-agent vision --model openai/gpt-4o "What menu is open?"

# Longer timeout for complex analysis
desktop-agent vision --timeout 60 "List every button and its position"
```

### 5C. Integrating Vision into Workflows

Vision isn't a step type yet (it's a future addition), but you can use it in the `run_task` callback:

```python
from modular.vision_fallback import ask_vision

def smart_run_task(step, resolved_text):
    # Try analyze first
    result = run_analyze_command(step, resolved_text)
    if result.confidence < 0.5:
        # Fall back to vision
        vision_answer = ask_vision(resolved_text)
        return StepResult(status="done", passed=True, result=vision_answer)
    return result
```

---

## 6. What's Done vs. What's Next

### ✅ Done (this branch)

- [x] Types module — all 10 step types + 13 condition ops, JSON↔typed conversion
- [x] Template resolver — `{{path}}` with dotted access, deep resolution
- [x] Condition evaluator — injection-safe, all 13 ops, recursive and/or/not
- [x] Structural validator — IDs, nesting, limits, conditions, forbidden patterns
- [x] Deterministic evaluator — synchronous, injected deps, exception-based control flow
- [x] `wait_for` step type (new — not in open-cowork)
- [x] 85 unit tests covering all modules + cookbook integration tests
- [x] Vision fallback module — OpenRouter API client with model fallback chain
- [x] CLI commands — `vision`, `workflow validate`, `workflow run`
- [x] Updated help text in CLI
- [x] Committed on `workflow-dsl` branch

### 🔲 Not Done (explicitly deferred)

**1. Agent Loop Integration (the biggest gap)**

The `workflow run --live` command uses a stub `run_task` callback. It needs an LLM to interpret natural language task strings into desktop-agent commands. This is the agent loop:

```
Task text: "Open Firefox and navigate to Jira"
    │
    ▼
LLM breaks it into steps:
    1. desktop-agent ensure-app "Firefox"
    2. desktop-agent analyze --json
    3. (find URL bar element @e3)
    4. desktop-agent click @e3
    5. desktop-agent type "https://jira.company.com"
    6. desktop-agent key Enter
    7. desktop-agent wait-for-text "Dashboard"
    │
    ▼
Each step executes, result flows back to scope
```

This requires an LLM with tool-use capability. QuetzaCodetl wrappers (qwen, gemma, deepseek) can do this. The integration point is the `run_task` callback in `execute_workflow()`.

**2. Vision Step Type in DSL**

A `vision` step type that takes a screenshot and asks a vision model a question, binding the result to scope. This would be a 10th step type (or 11th, counting `wait_for`):

```json
{"id": "check-screen", "type": "vision",
 "question": "Is there a red error banner visible?",
 "save_as": "screen_check"}
```

The evaluator already supports duck-typed dispatch — adding a new step type requires:
- Adding a `VisionStep` dataclass to `types.py`
- Adding a case in `_execute_step()` in `evaluator.py`
- Adding validation rules in `validate.py`

**3. Workflow Persistence & Management**

The existing `task_system.py` records linear step sequences via macro recording. The workflow DSL is a separate system. They could be unified:
- Record a workflow from live steps
- Save validated workflows to the SQLite DB
- Search workflows semantically (reuse the embedding infrastructure)
- Track workflow run history with success rates

**4. Desktop-Agent-Specific Conditions**

The 13 condition ops are generic. Desktop-specific conditions would be useful:
- `screen_contains(text)` — OCR check for text on screen
- `element_visible(@ref)` — AT-SPI element presence
- `window_focused(name)` — window manager state

These would require a scope that includes the current screen state, which means injecting a `get_screen_state` callback into the evaluator.

**5. Workflow Web UI / SSE Streaming**

The `on_event` callback already streams events. Hooking this to a web UI (like open-cowork's SSE stream) would enable remote monitoring of workflow execution.

---

## 7. Design Decisions & Tradeoffs

### Synchronous Evaluator (not async)

**Decision:** Made the evaluator fully synchronous. Open-cowork's evaluator is async because Coasty API calls are HTTP. Desktop-agent commands are local (xdotool, pyautogui) and blocking.

**Tradeoff:** Parallel branches use `ThreadPoolExecutor` instead of `asyncio.gather()`. This works because desktop actions are I/O-bound (waiting for UI responses), not CPU-bound. If we ever add remote machine execution, we'd need to make `run_task` optionally async.

### Duck-Typed Step Dispatch (not isinstance chains)

**Decision:** The evaluator dispatches on `step.type` (a string) rather than using `isinstance(step, TaskStep)`. This means any object with a `.type` attribute works — you can pass plain objects without constructing typed dataclasses.

**Tradeoff:** Less type safety at runtime. The validator catches bad types before evaluation, so this is safe. If you modify step types, remember to update both the validator and the dispatch in `_execute_step()`.

### Exception-Based Control Flow

**Decision:** `succeed` and `fail` steps raise `_WorkflowTermination` exceptions rather than returning early. This allows deeply nested steps (inside loops, retry blocks, if branches) to exit the entire workflow.

**Tradeoff:** The `retry` step has to catch and re-raise carefully — `succeed` inside a retry body should propagate (not retry), while failures should retry. The current implementation handles this correctly (see `evaluator.py:199-208`).

### Template Scope — Flat with Dotted Access

**Decision:** The scope is a flat dict where step results are stored at top level (`scope["stepId"] = result_dict`), and templates use dotted paths (`{{stepId.field}}`).

**Tradeoff:** Name collisions are possible if a `save_as` conflicts with another step ID. The validator prevents reserved names (`inputs`, `vars`) but doesn't prevent user-chosen collisions. In parallel branches, "last write wins" on shared `save_as` names — documented as expected behavior.

### Condition.from_dict() Pattern

**Decision:** Conditions use a `from_dict()` classmethod that recursively parses sub-conditions. This is more Pythonic than open-cowork's TypeScript approach where conditions are plain objects validated by the type system.

**Tradeoff:** The `Condition` dataclass has nullable fields that are mutually exclusive (you use `left/right` OR `value` OR `conditions[]` OR `condition`). The validator enforces correctness before evaluation, but the type system doesn't prevent constructing an invalid Condition directly.

---

## 8. Known Issues & Limitations

### Evaluator

1. **Cyclomatic complexity** — `_execute_step()` has a complexity of ~55 due to the 10-case dispatch. This is expected for a step evaluator pattern but triggers lint warnings. Extracting each step type to its own function would reduce it.

2. **Parallel branch exceptions** — If one parallel branch raises and another is still running, the ThreadPoolExecutor will let the running branch finish (it won't cancel it). This matches open-cowork's behavior.

3. **Scope is not thread-safe** — Parallel branches share a single `scope` dict. The current implementation relies on Python's GIL for dict operations. If we ever use true multi-processing, this needs a lock.

4. **`run_task` is synchronous** — The callback can't be a coroutine. If tasks need to be async (e.g., remote execution), the evaluator needs an `async def run_task` variant.

### Vision Fallback

5. **API key must be in environment** — The module reads `os.environ["OPENROUTER_API_KEY"]`. When running outside the visionproxy MCP context, you must `export` it manually.

6. **No local caching** — Repeated vision calls for the same screenshot will re-upload and re-bill. A content-hash-based cache could save cost.

7. **Model availability** — If Grok 4.3 is rate-limited or unavailable, the fallback chain tries gpt-4o and claude-sonnet-4. This adds latency (up to 3 HTTP calls before failure).

### CLI

8. **`workflow run --live` is a stub** — The `live_run_task` callback prints the task text but doesn't execute real desktop actions. See "Agent Loop Integration" in the TODO section.

9. **No workflow file watching** — `workflow validate` is one-shot. A `--watch` mode that re-validates on file changes would improve the editing workflow.

10. **Vision command doesn't stream** — The response arrives all at once after the API call completes. For very large screenshots, this can take 10-30 seconds with no progress indicator.

---

## 9. Rollback Plan

### To discard everything and go back:

```bash
cd /home/mal/AI/desktop-agent
git checkout experimental-analyze-v2
# The workflow-dsl branch remains for reference but is detached from HEAD
```

### To keep the vision fallback but remove the workflow DSL:

```bash
git checkout experimental-analyze-v2
git checkout workflow-dsl -- modular/vision_fallback.py
# Then revert the CLI changes manually or cherry-pick just the vision parts
```

### To keep the workflow DSL but remove the CLI changes:

```bash
git checkout experimental-analyze-v2 -- modular/cli.py
# The workflow module still exists and can be imported programmatically
```

### What the branch touches:

```
NEW:  modular/workflow/           (7 files, ~1900 lines)
NEW:  modular/vision_fallback.py  (1 file,  ~200 lines)
MOD:  modular/cli.py              (~100 lines added, ~3 lines changed)
```

No existing files were modified other than `cli.py`. The `analyze.py`, `input.py`, `window.py`, `ocr.py`, `atspi.py`, `config.py`, and `task_system.py` files are completely untouched.

---

## 10. OpenRouter Credential Info

The vision fallback uses the same credentials as the `visionproxy` MCP server.

**Key location in config:**
```
/home/mal/.claude/local-settings.json → mcpServers.visionproxy.env.OPENROUTER_API_KEY
```

**Key prefix:** `sk-or-v1-...`

**Default model:** `x-ai/grok-4.3`

**Endpoint:** `https://openrouter.ai/api/v1/chat/completions`

**Fallback models configured in `vision_fallback.py`:**
1. `x-ai/grok-4.3` (primary)
2. `openai/gpt-4o` (fallback 1)
3. `anthropic/claude-sonnet-4-20250514` (fallback 2)

**To override:** Set `OPENROUTER_API_KEY` and optionally `OPENROUTER_MODEL` in your environment.

---

## 11. Source Material

The workflow DSL is adapted from [open-cowork](https://github.com/coasty-ai/open-cowork) (MIT license), specifically:

| open-cowork source | desktop-agent equivalent | Adaptation |
|---|---|---|
| `packages/core/src/workflow/validate.ts` | `modular/workflow/validate.py` | Ported TS→Python, added `wait_for` validation |
| `packages/core/src/workflow/evaluator.ts` | `modular/workflow/evaluator.py` | Ported TS→Python, sync instead of async, added `wait_for`, removed cost tracking |
| `packages/core/src/workflow/conditions.ts` | `modular/workflow/conditions.py` | Near-verbatim port, same 13 ops, same `isEqual` semantics |
| `packages/core/src/workflow/template.ts` | `modular/workflow/template.py` | Near-verbatim port, same `FULL_REF`/`EMBEDDED_REF` regex |
| `packages/core/src/types.ts` | `modular/workflow/types.py` | Adapted types, added `WaitForStep`, dataclasses instead of TS interfaces |

Key differences from open-cowork:
- **No cost tracking** — `costCents`, `budgetCents`, `spentCents` removed (local-first, no billing)
- **No Coasty API types** — `cua_version`, `on_awaiting_human`, webhook secrets removed
- **No `machine_id`** — desktop-agent always targets the local screen
- **Added `wait_for`** — screen polling step type (not in open-cowork)
- **Added `timeout_seconds` on tasks** — optional time limit per task step
- **Synchronous** — desktop commands are local and blocking, not HTTP

---

*Generated 2026-06-16. Branch: `workflow-dsl`. Commit: `65ca74b`.*
