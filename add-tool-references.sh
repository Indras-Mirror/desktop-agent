#!/bin/bash
# Add user's common CLI tools as reference micro-tasks
# These help desktop-agent understand what tools are available

# Note: These are NOT recorded interactively - they're just reference docs

echo "Adding tool reference micro-tasks to database..."

# Create a SQL script to insert these directly
sqlite3 ~/.cache/desktop-agent/tasks.db <<EOF
-- User's common CLI tools as reference

INSERT OR IGNORE INTO tasks (name, description, purpose, context, steps_json) VALUES
('ref-batch-klein-queue',
 'batch-klein-queue - Process image folders from queue.txt with Klein',
 'Batch image generation/processing',
 'Reference: User has this in ~/.local/bin/',
 '[{"command":"type","args":["batch-klein-queue"],"description":"Run batch-klein-queue"}]'),

('ref-browser-agent',
 'browser-agent - Wrapper for agent-browser CLI',
 'Headless browser automation',
 'Reference: User has this in ~/.local/bin/',
 '[{"command":"type","args":["browser-agent"],"description":"Run browser-agent"}]'),

('ref-wrapper-help',
 'wrapper-help - Show all Claude Code wrapper scripts',
 'View available Claude wrappers',
 'Reference: User has this in ~/.local/bin/',
 '[{"command":"type","args":["wrapper-help"],"description":"Run wrapper-help"}]'),

('ref-quetza',
 'quetza - User'\''s AI model interaction tool',
 'Interact with local AI models',
 'Reference: User has this in ~/.local/bin/',
 '[{"command":"type","args":["quetza"],"description":"Run quetza"}]'),

('ref-llama-clean',
 'llama-clean - Kill all llama processes',
 'Clean up stuck llama-server instances',
 'Reference: From bash alias',
 '[{"command":"type","args":["llama-clean"],"description":"Run llama-clean"}]'),

('ref-opencode-clean',
 'opencode-clean - Kill all opencode processes',
 'Clean up stuck opencode instances',
 'Reference: From bash alias',
 '[{"command":"type","args":["opencode-clean"],"description":"Run opencode-clean"}]');

EOF

echo "✓ Added 6 tool reference tasks"
echo ""
echo "View them with: desktop-agent tasks | grep ref-"
