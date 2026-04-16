#!/bin/bash
# Quick recording script for foundational tasks
# Run each section manually to record the tasks

set -e

echo "==================================="
echo "Desktop Agent - Foundational Tasks"
echo "==================================="
echo ""
echo "This script will help you record 20+ foundational tasks."
echo "Each task will be recorded step-by-step."
echo ""
echo "Press ENTER to start..."
read

# Category 1: System Inspection
echo ""
echo "=== CATEGORY 1: System Inspection (5 tasks) ==="
echo ""

echo "Task 1/20: check-clipboard-content"
echo "Steps: Open terminal → type 'xclip -o' → Enter"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'xclip -o'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task check-clipboard-content \
  --description "Display current clipboard content in terminal" \
  --purpose "Verify clipboard before paste operations" \
  --context "Before pasting into important documents"
echo "✓ Task 1/20 saved!"
sleep 1

echo ""
echo "Task 2/20: check-running-apps"
echo "Steps: Press Super → type 'system monitor' → Enter"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'system monitor'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task check-running-apps \
  --description "Open System Monitor to view running applications" \
  --purpose "Verify which applications are currently running" \
  --context "Before launching apps or debugging issues"
echo "✓ Task 2/20 saved!"
sleep 1

echo ""
echo "Task 3/20: check-internet-connection"
echo "Steps: Open terminal → ping 8.8.8.8 -c 3"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'ping 8.8.8.8 -c 3'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task check-internet-connection \
  --description "Ping Google DNS to verify internet connectivity" \
  --purpose "Pre-validate web-dependent tasks" \
  --context "Before starting downloads or web searches"
echo "✓ Task 3/20 saved!"
sleep 1

echo ""
echo "Task 4/20: maximize-current-window"
echo "Steps: Press Super+Up"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super+Up"
read -p "Press ENTER after pressing Super+Up"
desktop-agent save-task maximize-current-window \
  --description "Maximize the currently focused window" \
  --purpose "Quick window management" \
  --context "When you need to see full application window"
echo "✓ Task 4/20 saved!"
sleep 1

echo ""
echo "Task 5/20: tile-windows-horizontal"
echo "Steps: Super+Left → Alt+Tab → Super+Right"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super+Left"
read -p "Press ENTER after pressing Super+Left"
echo "Now: Press Alt+Tab"
read -p "Press ENTER after pressing Alt+Tab"
echo "Now: Press Super+Right"
read -p "Press ENTER after pressing Super+Right"
desktop-agent save-task tile-windows-horizontal \
  --description "Tile two windows side-by-side (left and right)" \
  --purpose "Split screen workspace" \
  --context "When working with two apps simultaneously"
echo "✓ Task 5/20 saved!"
sleep 1

# Category 2: File Operations
echo ""
echo "=== CATEGORY 2: File Operations (5 tasks) ==="
echo ""

echo "Task 6/20: find-file-by-name (with parameter)"
echo "Steps: Open terminal → find ~ -name '*.py' -type f | head -20"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'find ~ -name \"*.py\" -type f | head -20'"
echo "(We'll make this parameterized later)"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task find-file-by-name \
  --description "Search filesystem for files matching pattern" \
  --purpose "Locate files when you don't know exact path" \
  --context "Finding configuration files or source code"
echo "✓ Task 6/20 saved!"
sleep 1

echo "Task 7/20: check-disk-space"
echo "Steps: Open terminal → df -h"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'df -h'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task check-disk-space \
  --description "View disk space usage across all partitions" \
  --purpose "Monitor storage capacity" \
  --context "Before large downloads or installations"
echo "✓ Task 7/20 saved!"
sleep 1

echo "Task 8/20: create-directory-structure"
echo "Steps: Open terminal → mkdir -p ~/test-project/{src,docs,tests}"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'mkdir -p ~/test-project/{src,docs,tests}'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task create-directory-structure \
  --description "Create project directory structure with subdirectories" \
  --purpose "Scaffold new project with standard folders" \
  --context "Starting new development projects"
echo "✓ Task 8/20 saved!"
sleep 1

echo "Task 9/20: extract-text-to-file"
echo "Steps: Ctrl+c → Open gedit → Ctrl+v → Ctrl+s → filename → Return"
echo "(Make sure you have some text selected before starting)"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Ctrl+c (copy selected text)"
read -p "Press ENTER after copying"
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'gedit'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 2
echo "Now: Press Ctrl+v (paste)"
read -p "Press ENTER after pasting"
echo "Now: Press Ctrl+s (save)"
read -p "Press ENTER after pressing Ctrl+s"
echo "Now: Type 'extracted-text.txt'"
read -p "Press ENTER after typing filename"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task extract-text-to-file \
  --description "Copy selected text and save to new file" \
  --purpose "Extract content from any application to text file" \
  --context "Saving important content from web or apps"
echo "✓ Task 9/20 saved!"
sleep 1

echo "Task 10/20: compress-folder"
echo "Steps: Open terminal → tar -czf test.tar.gz test-project/"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'tar -czf test.tar.gz test-project/'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task compress-folder \
  --description "Create compressed archive of directory" \
  --purpose "Archive and compress directories" \
  --context "Before moving or backing up projects"
echo "✓ Task 10/20 saved!"
sleep 1

# Category 3: Development Workflows
echo ""
echo "=== CATEGORY 3: Development Workflows (5 tasks) ==="
echo ""

echo "Task 11/20: git-status-check"
echo "Steps: Open terminal → cd ~/AI/desktop-agent → git status"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'cd ~/AI/desktop-agent'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
echo "Now: Type 'git status'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task git-status-check \
  --description "Check current git repository status" \
  --purpose "View uncommitted changes and branch info" \
  --context "Before commits or switching branches"
echo "✓ Task 11/20 saved!"
sleep 1

echo "Task 12/20: git-commit-workflow"
echo "Steps: terminal → cd repo → git add . → git commit -m msg"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'cd ~/AI/desktop-agent'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
echo "Now: Type 'git add .'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
echo "Now: Type 'git commit -m \"Update task repository\"'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task git-commit-workflow \
  --description "Stage all changes and create git commit" \
  --purpose "Quick commit during development" \
  --context "Saving work in progress"
echo "✓ Task 12/20 saved!"
sleep 1

echo "Task 13/20: code-and-terminal-split"
echo "Steps: Open code → Super+Left → Open terminal → Super+Right"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'code'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 2
echo "Now: Press Super+Left"
read -p "Press ENTER after pressing Super+Left"
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 2
echo "Now: Press Super+Right"
read -p "Press ENTER after pressing Super+Right"
desktop-agent save-task code-and-terminal-split \
  --description "Open VS Code and Terminal in split screen" \
  --purpose "Development environment setup" \
  --context "Starting coding session"
echo "✓ Task 13/20 saved!"
sleep 1

echo "Task 14/20: paste-without-formatting"
echo "Steps: Press Ctrl+Shift+v"
echo "Press ENTER when ready to record..."
read
desktop-agent record
echo "Now: Press Ctrl+Shift+v"
read -p "Press ENTER after pressing Ctrl+Shift+v"
desktop-agent save-task paste-without-formatting \
  --description "Paste clipboard content as plain text" \
  --purpose "Avoid formatting issues when pasting" \
  --context "Pasting into text editors or terminals"
echo "✓ Task 14/20 saved!"
sleep 1

echo "Task 15/20: count-words-in-selection"
echo "Steps: Ctrl+c → terminal → wc -w <<< \"$(xclip -o)\""
echo "Press ENTER when ready to record (select some text first)..."
read
desktop-agent record
echo "Now: Press Ctrl+c"
read -p "Press ENTER after copying"
echo "Now: Press Super"
read -p "Press ENTER after pressing Super"
echo "Now: Type 'terminal'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
sleep 1
echo "Now: Type 'wc -w <<< \"\$(xclip -o)\"'"
read -p "Press ENTER after typing"
echo "Now: Press Return"
read -p "Press ENTER after pressing Return"
desktop-agent save-task count-words-in-selection \
  --description "Count words in selected/copied text" \
  --purpose "Check document length quickly" \
  --context "Writing or editing documents"
echo "✓ Task 15/20 saved!"
sleep 1

echo ""
echo "==================================="
echo "✓ RECORDED 15 FOUNDATIONAL TASKS!"
echo "==================================="
echo ""
echo "You now have:"
echo "  • 5 system inspection tasks"
echo "  • 5 file operation tasks"
echo "  • 5 development workflow tasks"
echo ""
echo "View them with: desktop-agent tasks"
echo "Search with: desktop-agent tasks search \"<query>\""
echo "Use with: desktop-agent replay --run \"<task-name>\""
echo ""
echo "To record more advanced tasks, see:"
echo "  ~/AI/desktop-agent/TASK_REPOSITORY_ROADMAP.md"
echo ""
