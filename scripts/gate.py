#!/usr/bin/env python3
"""The door gate for one book: three checks, in seconds, nothing heavier.

    python scripts/gate.py books/bram-stoker_dracula
    python scripts/gate.py books/*            # every folder under books/

This is deliberately the whole gate — no corpus-wide analysis, no band-word
scans, no cross-library measurement. Kihea was explicit that a slow add
path is a reason not to use the workflow at all, and a book is inert text
with a citation: the two risks worth checking are "may we publish this" and
"is the file intact," and both are answerable in seconds.

What "may we publish this" means here, precisely, and just as importantly
what it does not mean: the book's own rights metadata cites a licence URI
this library has agreed to accept (scripts/selib.py's
ACCEPTED_LICENCE_URIS), checked by parsing every URL in that metadata as a
URL — scheme, host and path as whole values — not by searching for the
allow-listed string as a substring. That confirms the book's metadata
states an accepted licence and that the file is intact. It does NOT
confirm the underlying copyright claim is true, and no per-book check
against Standard Ebooks' own site happens here or anywhere else in this
repository today. These 614 books came from Standard Ebooks, whose
editions each carry a public-domain dedication in their own metadata;
nobody has independently re-verified each work's copyright status against
an outside source. If a check-at-source is wanted later, it is separate
work this repository does not yet do.

A restrictive-reading phrase (see selib.py's ADVISORY_RESTRICTIVE_PHRASES)
found beside an accepted licence URI does not fail the book — it is
recorded in provenance.json's terms.advisory_restrictive_phrases and
printed here, for a person to look at, never for the gate to decide on.
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selib  # noqa: E402


def check_book_folder(folder):
    """Returns (reasons, advisory) — `reasons` decides pass/fail, `advisory`
    never does. A non-empty `advisory` alongside an empty `reasons` is still
    a passing book; it is printed anyway, for a human to see."""
    reasons = []
    book_path = os.path.join(folder, "book.json")
    prov_path = os.path.join(folder, "provenance.json")

    if not os.path.exists(book_path):
        return ["no book.json"], []
    if not os.path.exists(prov_path):
        return ["no provenance.json"], []

    try:
        with open(book_path, "r", encoding="utf-8") as f:
            book = json.load(f)
    except Exception as exc:  # noqa: BLE001
        return ["book.json does not parse: %s" % exc], []

    try:
        with open(prov_path, "r", encoding="utf-8") as f:
            prov = json.load(f)
    except Exception as exc:  # noqa: BLE001
        return ["provenance.json does not parse: %s" % exc], []

    # Two routes onto the shelf, each with the checks its source can honestly
    # bear. Standard Ebooks books carry a CC0 dedication in their own
    # metadata; hand-added books (scripts/add_book.py — patents, retypeset
    # Gutenberg titles) instead record where their terms were read and quote
    # them, against selib.ACCEPTED_HAND_TERMS_URIS.
    route = (prov.get("how_we_got_it") or {}).get("route", "")
    hand = bool(route) and not route.startswith("Standard Ebooks")

    if not prov.get("terms", {}).get("read_at"):
        reasons.append("no citable public page in provenance.terms.read_at")

    if hand:
        if not (prov.get("identifier") or "").startswith("https://"):
            reasons.append("provenance.identifier is not a resolvable page")
        if prov.get("terms", {}).get("licence_uri") not in selib.ACCEPTED_HAND_TERMS_URIS:
            reasons.append("terms.licence_uri is not one this library accepts for hand-added books")
        if not (prov.get("terms", {}).get("as_stated_by_the_source") or "").strip():
            reasons.append("terms.as_stated_by_the_source is empty — the terms have to be quoted, not assumed")
    else:
        # identifier and provenance are extractable, and resolve to a real page
        if not selib.is_standardebooks_identifier(prov.get("identifier")):
            reasons.append("provenance.identifier is not a resolvable standardebooks.org page")

        # the recorded rights text cites a licence URI this library accepts,
        # with no disallowed licence URI also present — a structural check on
        # parsed URLs, not a reading of the prose around them
        stated = prov.get("terms", {}).get("as_stated_by_the_edition", "")
        if not selib.is_genuine_public_domain_dedication(stated):
            reasons.append("no accepted licence URI recorded in provenance.terms.as_stated_by_the_edition")

    # the file parses and its reading order resolves
    chapters = book.get("chapters", [])
    if not chapters:
        reasons.append("book.json has no chapters — reading order did not resolve")
    else:
        for i, ch in enumerate(chapters):
            if "blocks" not in ch:
                reasons.append("chapter %d has no blocks" % i)
                break

    # a restrictive-reading phrase never fails a book — surfaced separately
    # from `reasons` so it can never accidentally decide the gate
    advisory = prov.get("terms", {}).get("advisory_restrictive_phrases") or []

    return reasons, advisory


def main():
    args = sys.argv[1:]
    if not args:
        args = sorted(glob.glob(os.path.join("books", "*")))
        args = [a for a in args if os.path.isdir(a)]

    t0 = time.time()
    failed = 0
    advisory_count = 0
    for folder in args:
        if not os.path.isdir(folder):
            continue
        reasons, advisory = check_book_folder(folder)
        if reasons:
            failed += 1
            print("FAIL %s" % folder)
            for r in reasons:
                print("  - %s" % r)
        else:
            print("ok   %s" % folder)
        if advisory:
            advisory_count += 1
            print("  ADVISORY (did not fail this book, worth a look): %s" % ", ".join(advisory))
    elapsed = time.time() - t0
    print("gate: %d folder(s) in %.3fs (%.4fs/book)" % (len(args), elapsed, elapsed / max(len(args), 1)))
    if advisory_count:
        print("folders with an advisory flag: %d" % advisory_count)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
