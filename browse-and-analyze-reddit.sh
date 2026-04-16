#!/bin/bash
# Complete workflow: Browse Reddit + Extract posts
# Uses desktop-agent task recording + OCR analysis

set -e

echo "🌐 Opening Firefox and browsing Reddit..."
echo ""

# Run the recorded task
desktop-agent replay --run browse-reddit-feed

echo ""
echo "📊 Analyzing feed content..."
echo ""

# Wait for screenshot to be written
sleep 1

# Analyze the screenshot
python3 /home/mal/AI/desktop-agent/analyze-reddit-feed.py /tmp/reddit-feed.png

echo ""
echo "✓ Complete! Reddit feed analyzed."
