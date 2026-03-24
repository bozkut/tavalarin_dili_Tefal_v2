#!/usr/bin/env python
"""Wrapper to set API key and run find_letters_ai.py"""

import os
import sys
import subprocess

# API anahtarını ayarla
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # Set via environment variable

# find_letters_ai.py'yi çalıştır
from find_letters_ai import find_letters

if __name__ == "__main__":
    # Komut satırı argümanlarını geç
    sys.argv = [
        "find_letters_ai.py",
        "--input", r"E:\Tefal\Görseller\Tavalar",
        "--output", "./output/letters",
        "--color", "green"
    ]
    find_letters()
