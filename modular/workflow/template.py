"""
`{{path}}` template resolution for the workflow DSL.

Paths are dotted lookups into the run scope:
    {{inputs.x}}    — workflow input parameter
    {{vars.y}}      — runtime variable (e.g., retry attempt)
    {{stepIdOrSaveAs.field}} — bound step result field

Mirrors open-cowork's template.ts semantics exactly:
    - Exact `{{ref}}` returns the raw resolved value (preserving type)
    - Embedded refs interpolate each as string; missing → ''; objects → JSON
    - Non-strings returned unchanged
"""

import re
from typing import Any, Dict

# A scope is just a nested dict: {"inputs": {...}, "vars": {...}, "stepId": {...}, ...}
TemplateScope = Dict[str, Any]

FULL_REF = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")
EMBEDDED_REF = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def resolve_path(path: str, scope: TemplateScope) -> Any:
    """Resolve a dotted path into a scope object. Missing segments → None."""
    segments = path.split(".")
    current: Any = scope
    for seg in segments:
        if current is None:
            return None
        if not isinstance(current, dict):
            return None
        current = current.get(seg)
    return current


def resolve_template(value: Any, scope: TemplateScope) -> Any:
    """Resolve template references in a value.

    - A string that is EXACTLY one `{{ref}}` returns the raw resolved value
      (preserving its type — int, bool, dict, list, ...). Missing → None.
    - A string with embedded refs interpolates each as a string;
      missing refs → '' and objects → JSON.
    - Non-strings returned unchanged.
    """
    if not isinstance(value, str):
        return value

    full = FULL_REF.match(value)
    if full:
        return resolve_path(full.group(1), scope)

    def _replace(m: re.Match) -> str:
        path = m.group(1)
        resolved = resolve_path(path, scope)
        if resolved is None:
            return ""
        if isinstance(resolved, (dict, list)):
            import json
            return json.dumps(resolved)
        return str(resolved)

    return EMBEDDED_REF.sub(_replace, value)


def resolve_deep(value: Any, scope: TemplateScope) -> Any:
    """Recursively resolve templates inside plain objects/arrays/strings."""
    if isinstance(value, str):
        return resolve_template(value, scope)
    if isinstance(value, list):
        return [resolve_deep(v, scope) for v in value]
    if isinstance(value, dict):
        return {k: resolve_deep(v, scope) for k, v in value.items()}
    return value
