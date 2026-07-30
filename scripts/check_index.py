#!/usr/bin/env python3
"""Regenerate LIBRARY.md from the committed books/INDEX.json and fail if it
drifts from what's on disk. Does not touch the archives or re-scan any
zips — this is the "two artifacts kept in step" check, not the ingest.

    python scripts/check_index.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest import write_library_md, INDEX_PATH, LIBRARY_MD_PATH  # noqa: E402


def main():
    if not os.path.exists(INDEX_PATH):
        print("no books/INDEX.json — nothing to check")
        return 0

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)

    before = None
    if os.path.exists(LIBRARY_MD_PATH):
        with open(LIBRARY_MD_PATH, "r", encoding="utf-8") as f:
            before = f.read()

    write_library_md(index)

    with open(LIBRARY_MD_PATH, "r", encoding="utf-8") as f:
        after = f.read()

    if before != after:
        print("LIBRARY.md is stale: it does not match what books/INDEX.json generates.")
        print("Run `python scripts/ingest.py` (or this script) and commit the result.")
        return 1

    print("LIBRARY.md matches books/INDEX.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
