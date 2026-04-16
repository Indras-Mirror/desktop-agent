#!/usr/bin/python3
"""
Analyze Reddit feed from screenshot using OCR
Extracts post titles, subreddits, and upvotes
"""

import sys
from pathlib import Path

try:
    from PIL import Image
    import pytesseract
except ImportError:
    print("Error: Required dependencies not found")
    print("Install with: pip3 install pillow pytesseract")
    sys.exit(1)

def extract_reddit_posts(image_path):
    """Extract Reddit posts from screenshot using OCR"""
    img = Image.open(image_path)

    # Extract all text with positions
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    # Combine text into lines based on y-position
    lines = {}
    for i, word in enumerate(data['text']):
        if word.strip():
            y = data['top'][i]
            conf = data['conf'][i]

            # Group words by approximate y-position (within 10 pixels)
            line_y = (y // 10) * 10

            if line_y not in lines:
                lines[line_y] = []

            lines[line_y].append({
                'text': word,
                'x': data['left'][i],
                'conf': conf
            })

    # Sort by y position and reconstruct text
    sorted_lines = []
    for y in sorted(lines.keys()):
        # Sort words by x position within each line
        words = sorted(lines[y], key=lambda w: w['x'])
        line_text = ' '.join([w['text'] for w in words])
        sorted_lines.append(line_text)

    # Extract Reddit-specific patterns
    posts = []
    current_post = {}

    for line in sorted_lines:
        line_lower = line.lower()

        # Look for subreddit indicators
        if line.startswith('r/') or '/r/' in line_lower:
            if current_post:
                posts.append(current_post)
            current_post = {'subreddit': line, 'title': '', 'meta': ''}

        # Look for upvote counts (numbers followed by k or just numbers)
        elif any(char.isdigit() for char in line) and ('k' in line_lower or 'upvote' in line_lower):
            if 'meta' in current_post:
                current_post['meta'] += f" | {line}"

        # Otherwise treat as title or content
        elif line.strip() and len(line) > 10:
            if 'title' in current_post and not current_post['title']:
                current_post['title'] = line
            elif 'title' in current_post:
                current_post['title'] += f" {line}"

    if current_post:
        posts.append(current_post)

    return posts, sorted_lines

def main():
    if len(sys.argv) < 2:
        print("Usage: analyze-reddit-feed.py <screenshot-path>")
        sys.exit(1)

    screenshot_path = sys.argv[1]

    if not Path(screenshot_path).exists():
        print(f"Error: Screenshot not found: {screenshot_path}")
        sys.exit(1)

    print("🔍 Analyzing Reddit feed from screenshot...\n")

    posts, all_text = extract_reddit_posts(screenshot_path)

    if posts:
        print(f"📱 Found {len(posts)} posts:\n")
        for i, post in enumerate(posts, 1):
            print(f"Post {i}:")
            if post.get('subreddit'):
                print(f"  Subreddit: {post['subreddit']}")
            if post.get('title'):
                print(f"  Title: {post['title'][:100]}...")
            if post.get('meta'):
                print(f"  Meta: {post['meta']}")
            print()
    else:
        print("No structured posts found. Here's all extracted text:\n")
        print("=" * 60)
        for line in all_text:
            if line.strip():
                print(line)
        print("=" * 60)

    print(f"\n✓ Analysis complete! Screenshot: {screenshot_path}")

if __name__ == "__main__":
    main()
