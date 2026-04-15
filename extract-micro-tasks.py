#!/usr/bin/python3
"""
Analyze existing tasks and extract common micro-task patterns
"""

import json
import sqlite3
from pathlib import Path
from collections import Counter, defaultdict

DB_PATH = Path.home() / ".cache" / "desktop-agent" / "tasks.db"

def analyze_task_patterns():
    """Analyze all tasks and find repeated patterns"""

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, steps_json FROM tasks")
    tasks = c.fetchall()
    conn.close()

    # Pattern tracking
    patterns = defaultdict(list)

    for task_name, steps_json in tasks:
        steps = json.loads(steps_json)

        # Analyze step sequences
        for i in range(len(steps)):
            step = steps[i]
            cmd = step['command']
            args = step.get('args', [])

            # Single-step patterns
            if cmd == "key" and args:
                patterns[f"key_{args[0]}"].append(task_name)

            # Multi-step patterns
            if i + 2 < len(steps):
                # Pattern: Super → type X → Return (open app from Activities)
                if (steps[i]['command'] == 'key' and steps[i]['args'][0] == 'Super' and
                    steps[i+1]['command'] == 'type' and
                    steps[i+2]['command'] == 'key' and steps[i+2]['args'][0] == 'Return'):
                    app_name = steps[i+1]['args'][0]
                    patterns['open_app_from_activities'].append((task_name, app_name))

                # Pattern: type X → Return (terminal command)
                if (steps[i]['command'] == 'type' and
                    steps[i+1]['command'] == 'key' and steps[i+1]['args'][0] == 'Return'):
                    command = steps[i]['args'][0]
                    patterns['run_terminal_command'].append((task_name, command))

            if i + 1 < len(steps):
                # Pattern: Ctrl+c (copy)
                if (steps[i]['command'] == 'key' and steps[i]['args'][0] == 'Ctrl+a' and
                    steps[i+1]['command'] == 'key' and steps[i+1]['args'][0] == 'Ctrl+c'):
                    patterns['select_all_and_copy'].append(task_name)

    return patterns

def find_common_patterns(patterns, min_occurrences=3):
    """Filter patterns that appear at least min_occurrences times"""
    common = {}

    for pattern_name, occurrences in patterns.items():
        if len(occurrences) >= min_occurrences:
            common[pattern_name] = occurrences

    return common

def main():
    print("🔍 Analyzing task patterns...\n")

    patterns = analyze_task_patterns()
    common = find_common_patterns(patterns, min_occurrences=2)

    print(f"Found {len(common)} common patterns:\n")

    # Sort by frequency
    sorted_patterns = sorted(common.items(), key=lambda x: len(x[1]), reverse=True)

    for pattern_name, occurrences in sorted_patterns:
        count = len(occurrences)
        print(f"📌 {pattern_name}: {count} occurrences")

        # Show first few examples
        if isinstance(occurrences[0], tuple):
            # Has task name + data
            for task, data in occurrences[:5]:
                print(f"   - {task}: {data}")
        else:
            # Just task names
            for task in occurrences[:5]:
                print(f"   - {task}")

        if count > 5:
            print(f"   ... and {count - 5} more")
        print()

    print("\n✓ Pattern analysis complete!")
    print("\nRecommended micro-tasks to create:")
    print("1. open-app-from-activities (with param: app_name)")
    print("2. focus-url-bar (Ctrl+l)")
    print("3. run-terminal-command (with param: command)")
    print("4. select-all-and-copy (Ctrl+a → Ctrl+c)")
    print("5. paste-clipboard (Ctrl+v)")
    print("6. switch-window (Alt+Tab)")
    print("7. scroll-page-down (Page_Down)")

if __name__ == "__main__":
    main()
