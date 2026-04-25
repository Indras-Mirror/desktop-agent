from .config import (
    DB_PATH,
    EMBED_URL,
    RECORDING_FILE,
    RECORDING_ACTIVE,
    RECORDING_BUFFER,
    get_embedding,
    cosine_similarity,
)
import json
import time
import sqlite3


def load_recording():
    if RECORDING_FILE.exists():
        try:
            with open(RECORDING_FILE, "r") as f:
                data = json.load(f)
                return data.get("active", False), data.get("steps", [])
        except:
            pass
    return False, []


def save_recording(active, steps):
    with open(RECORDING_FILE, "w") as f:
        json.dump({"active": active, "steps": steps}, f)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            purpose TEXT,
            context TEXT,
            app_context TEXT,
            steps_json TEXT,
            embedding BLOB,
            success_rate REAL DEFAULT 1.0,
            last_used TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER,
            notes TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN parameters TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def start_recording():
    global RECORDING_ACTIVE, RECORDING_BUFFER
    RECORDING_ACTIVE = True
    RECORDING_BUFFER = []
    save_recording(True, [])
    print(
        "Recording started. Use desktop-agent commands normally, then save-task to save."
    )


def stop_recording():
    global RECORDING_ACTIVE
    RECORDING_ACTIVE = False
    steps = list(RECORDING_BUFFER)
    save_recording(False, [])
    return steps


def record_step(command, args, description=""):
    global RECORDING_BUFFER
    if not RECORDING_ACTIVE:
        return
    step = {
        "command": command,
        "args": args,
        "description": description,
        "timestamp": time.time(),
    }
    RECORDING_BUFFER.append(step)
    save_recording(True, RECORDING_BUFFER)


def save_task(
    name, description="", purpose="", context="", app_context="", parameters=None
):
    steps = stop_recording()
    if not steps:
        print("No steps recorded.")
        return False

    steps_json = json.dumps(steps)
    params_json = json.dumps(parameters) if parameters else None
    embed_text = f"{name}. {description}. {purpose}"
    embedding = get_embedding(embed_text)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO tasks (name, description, purpose, context, app_context, steps_json, parameters, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                name,
                description,
                purpose,
                context,
                app_context,
                steps_json,
                params_json,
                json.dumps(embedding) if embedding else None,
            ),
        )
        conn.commit()
        print(f"Task saved: {name}")
        if parameters:
            param_names = ", ".join([p["name"] for p in parameters])
            print(f"  Parameters: {param_names}")
        return True
    except sqlite3.IntegrityError:
        print(f"Task {name} already exists. Use tasks update to overwrite.")
        return False
    finally:
        conn.close()


def substitute_parameters(steps, param_values):
    substituted = []
    for step in steps:
        new_step = step.copy()
        new_args = []
        for arg in step["args"]:
            if isinstance(arg, str):
                for var_name, var_value in param_values.items():
                    arg = arg.replace(f"${{{var_name}}}", str(var_value))
            new_args.append(arg)
        new_step["args"] = new_args
        substituted.append(new_step)
    return substituted


def record_task_execution(task_id, success, error_details=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO task_runs (task_id, success, notes)
        VALUES (?, ?, ?)
    """,
        (task_id, 1 if success else 0, error_details or ""),
    )
    conn.commit()

    c.execute(
        """
        SELECT COUNT(*), SUM(success) FROM task_runs WHERE task_id = ?
    """,
        (task_id,),
    )
    total, successes = c.fetchone()

    if total > 0:
        success_rate = successes / total
        c.execute(
            """
            UPDATE tasks SET success_rate = ? WHERE id = ?
        """,
            (success_rate, task_id),
        )
        conn.commit()
    else:
        success_rate = 1.0

    conn.close()
    return success_rate if total > 0 else 1.0, total, successes or 0


def list_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT name, description, purpose, use_count, success_rate, created_at FROM tasks ORDER BY use_count DESC"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("No tasks saved.")
        return
    print(f"\nSaved Tasks ({len(rows)}):")
    for name, desc, purpose, use_count, success_rate, created in rows:
        if use_count > 0:
            indicator = (
                "✓" if success_rate >= 0.8 else "?" if success_rate >= 0.5 else "✗"
            )
            success_str = f" {indicator} {int(success_rate * 100)}%"
        else:
            success_str = ""

        print(f"  • {name}{success_str}")
        if desc:
            print(f"    {desc}")
        if purpose:
            print(f"    Purpose: {purpose}")
        print(f"    Used: {use_count}x | Created: {created[:10]}")


def search_tasks(query, limit=5, min_success_rate=0.0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT name, description, purpose, steps_json, success_rate, use_count
        FROM tasks
        WHERE success_rate >= ?
    """,
        (min_success_rate,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("No tasks to search.")
        return

    query_emb = get_embedding(query)
    if not query_emb:
        print("Search failed - could not embed query.")
        return

    results = []
    for name, desc, purpose, steps_json, success_rate, use_count in rows:
        if not desc:
            desc = ""
        stored_emb = get_embedding(f"{name}. {desc}. {purpose or ''}")
        if stored_emb:
            sim = cosine_similarity(query_emb, stored_emb)
            weighted_score = sim * (
                0.7 + 0.2 * success_rate + 0.1 * min(use_count / 10, 1.0)
            )
            results.append(
                (weighted_score, sim, name, desc, purpose, success_rate, use_count)
            )

    results.sort(reverse=True)

    print(f"\nSearch results for {query}:")
    for score, sim, name, desc, purpose, success_rate, use_count in results[:limit]:
        if use_count > 0:
            indicator = (
                "✓" if success_rate >= 0.8 else "?" if success_rate >= 0.5 else "✗"
            )
        else:
            indicator = " "
        print(f"  {indicator} [{int(sim * 100)}%] {name} (used {use_count}x)")
        if desc:
            print(f"    {desc}")
        if purpose:
            print(f"    Purpose: {purpose}")


def replay_task(query, param_values=None, dry_run=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, steps_json FROM tasks WHERE name = ?", (query,))
    row = c.fetchone()

    task_id = None
    task_name = query

    if not row:
        conn.close()
        query_emb = get_embedding(query)
        if query_emb:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, name, description, purpose, steps_json FROM tasks")
            rows = c.fetchall()
            conn.close()

            if not rows:
                print("No tasks found.")
                return None

            results = []
            for tid, name, desc, purpose, steps_json in rows:
                if not desc:
                    desc = ""
                stored_emb = get_embedding(f"{name}. {desc}. {purpose or ''}")
                if stored_emb:
                    sim = cosine_similarity(query_emb, stored_emb)
                    results.append((sim, tid, name, desc, purpose, steps_json))

            results.sort(reverse=True)

            if results:
                best = results[0]
                print(
                    f"Found task via semantic search: {best[2]} ({int(best[0] * 100)}% match)"
                )
                task_id, task_name, steps_json = best[1], best[2], best[5]
            else:
                print("No matching tasks found.")
                return None
        else:
            print("Could not embed query.")
            return None
    else:
        task_id, steps_json = row

    steps = json.loads(steps_json)

    if param_values:
        steps = substitute_parameters(steps, param_values)
        print(f"Applied parameters: {param_values}")

    print(f"\nTask: {task_name} ({len(steps)} steps)")
    for i, step in enumerate(steps, 1):
        desc = step.get("description", "")
        if not desc:
            cmd = step["command"]
            args_str = " ".join(str(a) for a in step.get("args", []))
            desc = f"{cmd} {args_str}"
        print(f"  {i}. {desc}")

    if dry_run:
        print("\n(Dry run - use replay --run to execute)")
        if task_id:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "UPDATE tasks SET use_count = use_count + 1, last_used = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id,),
            )
            conn.commit()
            conn.close()
        return steps

    print("\nExecuting task...")
    success = True
    error_msg = None
    failed_step = None

    try:
        from .input import execute_step

        for i, step in enumerate(steps, 1):
            desc = step.get("description", "")
            if not desc:
                cmd = step.get("command", "")
                args = step.get("args", [])
                desc = f"{cmd} {args}"
            print(f"[{i}/{len(steps)}] {desc}")
            execute_step(step)
            time.sleep(0.5)
        print("✓ Task completed successfully")
    except Exception as e:
        success = False
        failed_step = i
        error_msg = str(e)
        print(f"✗ Task failed at step {i}: {e}")

    if task_id:
        new_rate, total, successes = record_task_execution(task_id, success, error_msg)
        print(f"  Success rate: {int(new_rate * 100)}% ({successes}/{total} runs)")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET use_count = use_count + 1, last_used = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        conn.close()

    return steps


def delete_task(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE name = ?", (name,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"Deleted task: {name}")
    else:
        print(f"Task not found: {name}")


init_db()
RECORDING_ACTIVE, RECORDING_BUFFER = load_recording()
