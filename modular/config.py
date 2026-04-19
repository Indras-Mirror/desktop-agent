#!/usr/bin/python3
import subprocess
import sys
import os
import json
import time
import math
import sqlite3
import threading
import requests
import re
from pathlib import Path
from difflib import SequenceMatcher

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pyatspi

    ATSPI_AVAILABLE = True
except ImportError:
    ATSPI_AVAILABLE = False

try:
    import pytesseract

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

CACHE_DIR = Path.home() / ".cache" / "desktop-agent"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = CACHE_DIR / "tasks.db"

EMBED_URL = "http://localhost:9086/v1/embeddings"
EMBED_MODEL = "nomic"

RECORDING_FILE = CACHE_DIR / "recording.json"
SCREENSHOT_DIR = Path("/tmp/desktop-agent")
SCREENSHOT_DIR.mkdir(exist_ok=True)

ELEMENT_CACHE = {}
STABLE_ELEMENT_REGISTRY = {}
RECORDING_ACTIVE = False
RECORDING_BUFFER = []


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def get_embedding(text):
    try:
        resp = requests.post(
            EMBED_URL, json={"input": [text], "model": "nomic"}, timeout=10
        )
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"Warning: Embedding failed: {e}")
        return None


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b + 1e-8)


def get_primary_monitor():
    """Get primary monitor geometry (x, y, width, height)"""
    stdout, _, _ = run_cmd("xrandr --query | grep ' connected primary'")

    if stdout:
        # Parse: "DP-2 connected primary 3440x1440+1920+322 ..."
        match = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', stdout)
        if match:
            width, height, x, y = map(int, match.groups())
            return {"x": x, "y": y, "width": width, "height": height}

    # Fallback: try first connected monitor
    stdout, _, _ = run_cmd("xrandr --query | grep ' connected' | head -1")
    if stdout:
        match = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', stdout)
        if match:
            width, height, x, y = map(int, match.groups())
            return {"x": x, "y": y, "width": width, "height": height}

    # Ultimate fallback
    return {"x": 0, "y": 0, "width": 1920, "height": 1080}


# Cache primary monitor geometry
PRIMARY_MONITOR = get_primary_monitor()
