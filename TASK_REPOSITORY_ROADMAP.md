# Desktop Agent - Task Repository Roadmap

**38 High-Value Tasks to Add**

Current: **14 tasks**  
Target: **52+ tasks** covering all common Linux desktop workflows

---

## Priority 1: Foundational Tasks (Essential Building Blocks)

These enable other tasks and provide critical system awareness.

### System Inspection & Navigation

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 1 | `check-running-apps` | Verify what's running before launching | Super → system monitor → view processes | - |
| 2 | `check-clipboard-content` | Validate clipboard before paste | Terminal → xclip -o | - |
| 3 | `check-internet-connection` | Pre-validate web tasks | Terminal → ping 8.8.8.8 | - |
| 4 | `get-current-workspace` | Know which virtual desktop | Terminal → wmctrl -d | - |
| 5 | `enumerate-windows-by-app` | List all windows for app (multi-window) | xdotool search --class ${app} | app |
| 6 | `maximize-current-window` | Maximize focused window | Super+Up OR xdotool key Super+Up | - |
| 7 | `tile-windows-horizontal` | Split screen left/right | Super+Left, Alt+Tab, Super+Right | - |
| 8 | `close-all-windows-of-app` | Bulk close (e.g., all Firefox windows) | xdotool search → kill by PID | app |

**Impact:** Every other task will use these as dependencies or validations.

---

## Priority 2: File Operations (Core Desktop Work)

### File Management

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 9 | `create-directory-structure` | Scaffold new projects | Terminal → mkdir -p ${path}/{src,docs,tests} | path |
| 10 | `find-file-by-name` | Locate files anywhere | Terminal → find ~ -name "${pattern}" | pattern |
| 11 | `move-file-to-backup` | Safe file operations | Terminal → cp ${file} ~/backups/$(date +%s)_${file} | file |
| 12 | `bulk-rename-files` | Rename multiple files | File manager → select → F2 → rename pattern | pattern |
| 13 | `compress-folder` | Archive directories | Terminal → tar -czf ${name}.tar.gz ${folder} | folder, name |
| 14 | `extract-archive` | Unpack tar/zip | Terminal → tar -xzf ${file} OR unzip ${file} | file |
| 15 | `open-file-location` | Jump to file in file manager | Terminal → nautilus $(dirname ${file}) | file |
| 16 | `delete-to-trash` | Safe delete (recoverable) | File manager → select → Delete OR gio trash ${file} | file |

**Impact:** Handles 80% of file operations AI agents need.

---

## Priority 3: Development Workflows (For Coding Tasks)

### Git & Development

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 17 | `git-commit-workflow` | Stage + commit + push | Terminal → git add . → git commit -m "${msg}" → git push | msg, repo_path |
| 18 | `git-status-check` | View current changes | Terminal → cd ${repo} → git status | repo_path |
| 19 | `git-create-branch` | Start feature work | Terminal → git checkout -b ${branch} | branch, repo_path |
| 20 | `run-tests-and-report` | Test with output capture | Terminal → npm test 2>&1 \| tee test-results.txt | test_cmd |
| 21 | `start-dev-server` | Launch local server | Terminal → cd ${project} → ${start_cmd} | project, start_cmd |
| 22 | `stop-dev-server` | Kill dev server | Terminal → pkill -f "${process_name}" | process_name |
| 23 | `search-code-in-editor` | Find across files in VS Code | VS Code → Ctrl+Shift+F → type ${query} | query |
| 24 | `format-code-file` | Run formatter on current file | VS Code → Shift+Alt+F | - |
| 25 | `install-npm-package` | Add dependency | Terminal → cd ${project} → npm install ${package} | package, project |

**Impact:** Covers full development cycle from branch → code → test → commit.

---

## Priority 4: Documentation & Communication

### Text Processing

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 26 | `extract-text-to-file` | Save selected content | Ctrl+c → gedit → Ctrl+v → Ctrl+s → ${filename} | filename |
| 27 | `append-clipboard-to-notes` | Collect research snippets | Open ${notes_file} → Ctrl+End → Ctrl+v → Ctrl+s | notes_file |
| 28 | `create-markdown-doc` | New doc with template | Terminal → echo "# ${title}\n\n" > ${file}.md → gedit ${file}.md | title, file |
| 29 | `extract-urls-from-page` | Collect links | OCR → regex URLs → save to ${file} | file |
| 30 | `paste-without-formatting` | Plain text paste | Ctrl+Shift+v OR xdotool key ctrl+shift+v | - |
| 31 | `count-words-in-selection` | Check document length | Select → Ctrl+c → Terminal → wc -w <<< "$(xclip -o)" | - |

**Impact:** Research and documentation workflows become one-command operations.

---

## Priority 5: Media & Content

### Image/Video Processing

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 32 | `download-video-from-clipboard` | Archive media | Terminal → yt-dlp $(xclip -o) -o ${output} | output |
| 33 | `convert-image-format` | Change image type | Terminal → convert ${input} ${output} | input, output |
| 34 | `resize-image` | Optimize image size | Terminal → convert ${input} -resize ${size} ${output} | input, size, output |
| 35 | `batch-screenshot-sequence` | Document process | Loop: scrot → sleep ${interval} (for ${duration}) | interval, duration |
| 36 | `record-screen-video` | Screen recording | Terminal → ffmpeg -video_size ${size} -f x11grab -i :0.0 ${output} | size, output |
| 37 | `extract-audio-from-video` | Get audio track | Terminal → ffmpeg -i ${video} -vn ${audio}.mp3 | video, audio |

**Impact:** All media workflows automated.

---

## Priority 6: Multi-App Orchestration

### Complex Workflows

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 38 | `code-and-terminal-split` | Dev environment | Code → Super+Left, Terminal → Super+Right | - |
| 39 | `code-test-debug-cycle` | Development loop | Edit → Ctrl+s → Alt+Tab → npm test → view | project |
| 40 | `web-to-document` | Research → docs | Firefox search → select → copy → gedit → paste → format | query |
| 41 | `compare-two-files` | File diff | Terminal → meld ${file1} ${file2} | file1, file2 |
| 42 | `monitor-log-file` | Watch logs while working | Terminal → tail -f ${logfile} | logfile |
| 43 | `email-current-screenshot` | Quick sharing | Scrot → Thunderbird → attach → send to ${email} | email |
| 44 | `backup-and-edit` | Safe editing | move-file-to-backup → gedit ${file} | file |

**Impact:** Entire workflows (4+ apps) in one command.

---

## Priority 7: System Administration

### System Management

| # | Task Name | Purpose | Key Steps | Params |
|---|-----------|---------|-----------|---------|
| 45 | `check-disk-space` | View storage usage | Terminal → df -h; du -sh ~/* | - |
| 46 | `check-system-resources` | Monitor CPU/RAM | System Monitor → Resources tab | - |
| 47 | `kill-frozen-app` | Recover from hang | xkill → click window OR pkill ${process} | process |
| 48 | `restart-service` | Service management | Terminal → sudo systemctl restart ${service} | service |
| 49 | `check-network-ports` | Network debugging | Terminal → sudo netstat -tulpn \| grep LISTEN | - |
| 50 | `update-system-packages` | System updates | Terminal → sudo apt update && sudo apt upgrade -y | - |

**Impact:** System maintenance without manual intervention.

---

## Priority 8: Smart Compositions (After Parameters Working)

### High-Level Workflows

| # | Task Name | Composition | Purpose |
|---|-----------|-------------|---------|
| 51 | `full-research-workflow` | web-search → extract-text → append-to-notes | End-to-end research |
| 52 | `test-and-commit` | run-tests → (if success) git-commit | Safe commits |
| 53 | `setup-coding-workspace` | switch-workspace → code-and-terminal → start-dev-server | Full environment |
| 54 | `meeting-prep` | Open calendar → screenshot → create-markdown-doc | Meeting automation |
| 55 | `daily-backup` | compress-folder → move to backup drive → verify | Data protection |

**Impact:** One command for 5+ manual steps.

---

## Recording Strategy

### Week 1: Foundations (Priority 1-2)
- Record tasks 1-16
- **Goal:** System awareness + file operations
- **Time:** ~2 hours (8 mins per task)

### Week 2: Development (Priority 3-4)
- Record tasks 17-31
- **Goal:** Code workflows + documentation
- **Time:** ~2 hours

### Week 3: Advanced (Priority 5-6)
- Record tasks 32-44
- **Goal:** Media + multi-app workflows
- **Time:** ~2 hours

### Week 4: System + Composition (Priority 7-8)
- Record tasks 45-55
- **Goal:** System admin + smart compositions
- **Time:** ~2 hours

**Total:** 8 hours to build complete task library

---

## Quick Recording Template

```bash
#!/bin/bash
# Record a new task quickly

TASK_NAME="$1"
DESCRIPTION="$2"
PURPOSE="$3"

# Start recording
desktop-agent record

# DO THE STEPS (manually)
echo "Execute the task steps now..."
read -p "Press ENTER when done..."

# Save
desktop-agent save-task "$TASK_NAME" \
  --description "$DESCRIPTION" \
  --purpose "$PURPOSE"

echo "✓ Task saved: $TASK_NAME"
```

**Usage:**
```bash
./record-task.sh "check-running-apps" \
  "Open System Monitor to view running processes" \
  "Verify which applications are currently running"
```

---

## Success Metrics

After building this repository:

**Coverage:**
- ✓ 55 tasks covering all major desktop operations
- ✓ 90% of AI agent desktop needs met
- ✓ Average 3 task reuses per new workflow

**Quality:**
- ✓ 80%+ success rate on all tasks
- ✓ 95%+ semantic search accuracy
- ✓ <30 seconds to find + execute any workflow

**Efficiency:**
- ✓ 5 minutes to record new complex workflow
- ✓ 2 minutes to compose new task from existing ones
- ✓ 10x faster than manual GUI navigation

---

## Maintenance Plan

**Monthly:**
1. Review task success rates
2. Update broken tasks (UI changes, app updates)
3. Merge similar tasks
4. Extract new micro-tasks from patterns

**Quarterly:**
1. Add 10 new advanced tasks
2. Refactor compositions
3. Benchmark search accuracy
4. Update documentation

**Yearly:**
1. Full audit of all tasks
2. Remove deprecated tasks
3. Add new app integrations
4. Performance optimization

---

## Integration with AI Agents

Once repository is built, AI agents can:

```python
# Agent requests: "I need to search for Python automation docs and save them"

# Desktop-agent finds best matches:
search_results = search_tasks("search documentation save notes", limit=3)
# → "full-research-workflow" (92% match)
# → "web-to-document" (87% match)
# → "research-web-take-notes" (84% match)

# Agent executes:
replay_task("full-research-workflow", 
            param_values={"query": "Python automation"})
```

**Result:** AI agent learns your desktop patterns and completes tasks faster each time.

---

## Next: Start Recording

**Begin with the easiest high-value tasks:**

1. ✅ `check-clipboard-content` (30 seconds)
2. ✅ `maximize-current-window` (20 seconds)
3. ✅ `check-disk-space` (40 seconds)
4. ✅ `git-status-check` (30 seconds)
5. ✅ `extract-text-to-file` (45 seconds)

**Total:** 5 tasks in <5 minutes to validate the workflow.

Then tackle the full Priority 1 list (8 tasks, ~1 hour).

By end of month: **55-task repository making you 10x faster at Linux desktop automation.**
