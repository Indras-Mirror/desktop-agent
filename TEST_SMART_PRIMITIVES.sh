#!/bin/bash
# Test script for smart primitives improvements

echo "==================================================================="
echo "  Desktop Agent - Smart Primitives Test Suite"
echo "==================================================================="
echo ""

echo "📋 Testing improved features..."
echo ""

# Test 1: Smart click auto-detection
echo "━━━ Test 1: Smart Click Auto-Detection ━━━"
echo "Command: desktop-agent click \"Mozilla\""
echo "Expected: Should detect it's text and do OCR search"
echo ""
echo "Press Enter to run test 1..."
read

desktop-agent click "Mozilla" --verify "Firefox"
echo ""

# Test 2: Better OCR filtering
echo "━━━ Test 2: Better OCR Filtering ━━━"
echo "Command: desktop-agent find-text \"Firefox\" --max-results 3"
echo "Expected: Clean output, top 3 matches only"
echo ""
echo "Press Enter to run test 2..."
read

desktop-agent find-text "Firefox" --max-results 3
echo ""

# Test 3: Wait for window
echo "━━━ Test 3: Wait for Window ━━━"
echo "Command: desktop-agent wait-for-window \"Firefox\" --timeout 5"
echo "Expected: Should find Firefox window or timeout"
echo ""
echo "Press Enter to run test 3..."
read

desktop-agent wait-for-window "Firefox" --timeout 5
echo ""

# Test 4: Wait for text
echo "━━━ Test 4: Wait for Text ━━━"
echo "Command: desktop-agent wait-for-text \"Mozilla\" --timeout 5"
echo "Expected: Should find 'Mozilla' text on screen"
echo ""
echo "Press Enter to run test 4..."
read

desktop-agent wait-for-text "Mozilla" --timeout 5
echo ""

# Test 5: Wait for file (use existing file)
echo "━━━ Test 5: Wait for File ━━━"
echo "Command: desktop-agent wait-for-file \"~/.bash_history\" --timeout 5"
echo "Expected: Should find .bash_history immediately"
echo ""
echo "Press Enter to run test 5..."
read

desktop-agent wait-for-file "~/.bash_history" --timeout 5
echo ""

echo "==================================================================="
echo "  ✅ All tests completed!"
echo "==================================================================="
echo ""
echo "Review:"
echo "  - Smart click with text search"
echo "  - Better OCR filtering (clean output)"
echo "  - Wait commands (no more sleep guessing)"
echo "  - Clear ✓/✗/⏳ indicators"
echo ""
echo "Next: Test with a small model on real tasks!"
