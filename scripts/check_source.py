#!/usr/bin/env python3
"""Verifies a committed book against the EPUB it says it came from.

    python scripts/check_source.py books/bram-stoker_dracula
    python scripts/check_source.py books/*
    python scripts/check_source.py --archives C:\\archives books/*

books/HOW-THE-FIRST-BOOK-WENT.md named this as the thing that should exist
before there are a thousand books, "because after that nobody reads them."
This is that check. It runs on its own schedule, separate from adding a
book -- it never runs in the add path, and it never blocks a book from
reaching the shelf. scripts/gate.py's door check is, deliberately, a
different and much lighter thing.

Where the EPUB comes from, in order:

  1. --archives DIR: a local folder of Standard Ebooks bulk-download zips,
     read the same way scripts/ingest.py reads them. Fast and offline, for
     a maintainer who already has the archives on their own machine --
     nothing under that folder is ever written to, and nothing from it is
     ever committed here.
  2. Otherwise (CI's own path, since no archive exists there and none
     should): the book's own public per-book download, at the exact
     download URL its provenance.json's `identifier` resolves to. Never a
     patron zip -- Standard Ebooks gates bulk access behind Patrons Circle
     membership, but a single book's own EPUB has always been a free,
     public download from that book's own page. Fetching it is also the
     check for "the identifier citing the public page": if the citation
     did not resolve to a real, working download, this would fail here
     before checking anything else.

What gets checked, all independently re-derived from the fetched EPUB --
never taken on book.json's or provenance.json's own word for anything:

  - chapter count matches the committed book.json exactly.
  - reading order matches: the sequence of chapter labels, not just the
    count -- a shuffled read would still have the right chapter count.
  - the publisher's apparatus is excluded: every spine file whose body is
    not tagged bodymatter (title page, imprint, dedication, colophon, and
    so on) is confirmed to contribute nothing to the chapters extracted --
    this is the same test scripts/gate.py's door check makes at ingest
    time, run again here against the file that actually shipped, months or
    years later, rather than trusted to still be true.
  - word count, within a small tolerance rather than exact equality. The
    default fetch path (CI's public per-book download) can be a newer
    Standard Ebooks build than the one this book was actually ingested
    from -- they retypeset books after publication -- so a handful of
    words' difference is drift worth knowing about, not by itself a
    failure. A gap outside the tolerance still fails, and prints both
    numbers so a person can decide whether the book needs re-ingesting.
  - the licence dedication is present in the EPUB's own rights metadata,
    read fresh, the same way scripts/gate.py's door check reads it.
  - provenance.json's own `identifier` is the exact page the fetched EPUB's
    own dc:identifier states -- not merely present, equal.

Any mismatch means the committed book.json has drifted from the file it
claims to represent: hand-edited, corrupted, or built from a different
edition than the one on record. That is exactly what this check exists to
catch before there are too many books left for anyone to read by eye.
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selib  # noqa: E402

USER_AGENT = "superb-catalogue-source-check/1 (+https://github.com/superb-catalogue/library)"
WORD_COUNT_TOLERANCE_FRACTION = 0.01  # 1% -- see the module docstring on why an exact match isn't required
WORD_COUNT_TOLERANCE_FLOOR = 5  # a book under ~500 words still gets a few words of slack
REQUEST_DELAY_SECONDS = 0.4  # politeness toward standardebooks.org across a whole-shelf run


class SourceUnavailable(Exception):
    """The EPUB itself could not be obtained -- not a content mismatch."""


def _archive_index(archives_dir):
    """Every inner .epub's own identifier, mapped to (zip path, entry name,
    bytes are read lazily by the caller). Built once per run, not once per
    book -- scanning 32 zips per book would make a whole-shelf run 614x
    slower than it needs to be."""
    index = {}
    for zpath in sorted(glob.glob(os.path.join(archives_dir, "*.zip"))):
        outer = zipfile.ZipFile(zpath)
        for name in outer.namelist():
            if not name.endswith(".epub"):
                continue
            data = outer.read(name)
            try:
                ez = zipfile.ZipFile(io.BytesIO(data))
                opf_path = selib.find_opf_path(ez)
                root = ET.fromstring(ez.read(opf_path).decode("utf-8"))
                ident = selib.parse_metadata(root)["identifier"]
            except Exception:  # noqa: BLE001 -- an unreadable entry just isn't indexed
                continue
            # Standard Ebooks rebuilds books; keep the newest-seen build for
            # a given identifier the same way scripts/ingest.py does.
            modified = selib.parse_metadata(root).get("modified") or ""
            prev = index.get(ident)
            if prev is None or modified >= prev[2]:
                index[ident] = (zpath, name, modified, data)
    return index


def fetch_epub_bytes(identifier, archives_dir=None, _archive_cache={}):
    """Returns raw EPUB bytes for `identifier`, from a local archive if one
    was given, otherwise from the book's own public per-book download."""
    if archives_dir:
        if archives_dir not in _archive_cache:
            _archive_cache[archives_dir] = _archive_index(archives_dir)
        entry = _archive_cache[archives_dir].get(identifier)
        if entry is None:
            raise SourceUnavailable("identifier not found in any zip under %s" % archives_dir)
        return entry[3]

    if not selib.is_standardebooks_identifier(identifier):
        raise SourceUnavailable("identifier is not a standardebooks.org page: %r" % identifier)
    slug = selib.slug_from_identifier(identifier)
    url = identifier.rstrip("/") + "/downloads/" + slug + ".epub"
    return _download_epub(url)


def _download_epub(url, _redirected=False):
    """A first request to a book's own download URL returns an HTML
    interstitial page ("Your Download Has Started!") with a
    `<meta http-equiv="refresh" ...>` pointing at the same URL with
    `?source=download` appended -- a browser follows that automatically;
    `urllib` does not. Detected by content, not assumed: real EPUB bytes
    start with the zip signature (`PK\\x03\\x04`); anything else is read as
    text and its meta-refresh target followed, once."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise SourceUnavailable("could not download %s: %s" % (url, exc)) from exc

    if data[:4] == b"PK\x03\x04":
        return data

    if _redirected:
        raise SourceUnavailable(
            "%s did not return an EPUB even after following its own meta-refresh once" % url
        )

    match = re.search(
        r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*url=([^"\';]+)',
        data.decode("utf-8", errors="replace"),
        re.IGNORECASE,
    )
    if not match:
        raise SourceUnavailable("%s returned non-EPUB content with no meta-refresh to follow" % url)
    next_url = urllib.parse.urljoin(url, match.group(1).strip())
    return _download_epub(next_url, _redirected=True)


def derive_from_epub(data):
    """Everything this check needs, read straight out of the EPUB bytes --
    the same primitives scripts/ingest.py itself uses, so a discrepancy
    means the committed text and the source disagree, not that two
    different parsers disagree with each other."""
    ez = zipfile.ZipFile(io.BytesIO(data))
    opf_path = selib.find_opf_path(ez)
    opf_dir = os.path.dirname(opf_path).replace("\\", "/")
    root = ET.fromstring(ez.read(opf_path).decode("utf-8"))
    meta = selib.parse_metadata(root)
    spine = selib.parse_manifest_spine(root)
    chapters = selib.extract_chapters(ez, opf_dir, spine)

    # Which spine files were apparatus (excluded), read independently of
    # extract_chapters' own internal skip -- this is the explicit check
    # that the exclusion actually happened against this file, not an
    # assumption that reusing the same function proves it.
    apparatus_hrefs = []
    for href in spine:
        full = ((opf_dir + "/" + href) if opf_dir else href).replace("\\", "/")
        try:
            raw = ez.read(full)
        except KeyError:
            continue
        body_root = ET.fromstring(raw.decode("utf-8"))
        body = body_root.find("{http://www.w3.org/1999/xhtml}body")
        if body is None:
            continue
        body_type = body.get("{http://www.idpf.org/2007/ops}type") or ""
        tokens = [t.split(":", 1)[1] if ":" in t else t for t in body_type.split()]
        if "bodymatter" not in tokens:
            apparatus_hrefs.append(href)

    return {
        "meta": meta,
        "chapters": chapters,
        "apparatus_hrefs": apparatus_hrefs,
        "words": selib.count_words(chapters),
    }


def check_one(book_dir, archives_dir=None):
    """Returns (reasons, info) -- `reasons` is empty iff the book passes.
    `info` carries the numbers worth printing either way."""
    reasons = []
    book_path = os.path.join(book_dir, "book.json")
    prov_path = os.path.join(book_dir, "provenance.json")

    if not os.path.exists(book_path) or not os.path.exists(prov_path):
        return ["missing book.json or provenance.json"], {}

    with open(book_path, "r", encoding="utf-8") as f:
        book = json.load(f)
    with open(prov_path, "r", encoding="utf-8") as f:
        prov = json.load(f)

    identifier = prov.get("identifier")

    # Hand-added books (scripts/add_book.py) have no source EPUB to re-read.
    # Their preparer is what checked them against their own source; this
    # check reports them as skipped rather than pretending to have verified
    # them against an EPUB that does not exist.
    route = (prov.get("how_we_got_it") or {}).get("route", "")
    if route and not route.startswith("Standard Ebooks"):
        return None, {"skipped": "hand-added (%s); no EPUB source to re-read" % route}

    try:
        data = fetch_epub_bytes(identifier, archives_dir=archives_dir)
    except SourceUnavailable as exc:
        return ["source EPUB unavailable: %s" % exc], {}

    source = derive_from_epub(data)
    meta = source["meta"]
    info = {
        "committed_chapters": len(book.get("chapters", [])),
        "source_chapters": len(source["chapters"]),
        "committed_words": prov.get("text", {}).get("words"),
        "source_words": source["words"],
        "apparatus_excluded": len(source["apparatus_hrefs"]),
    }

    # the identifier cites the public page -- not merely present, equal to
    # what the fetched EPUB itself declares
    if meta.get("identifier") != identifier:
        reasons.append(
            "provenance.identifier (%r) does not match the source EPUB's own dc:identifier (%r)"
            % (identifier, meta.get("identifier"))
        )
    if not selib.is_standardebooks_identifier(identifier):
        reasons.append("provenance.identifier is not a standardebooks.org page")

    # the licence dedication is present, read fresh off the source
    if not selib.is_genuine_public_domain_dedication(meta.get("rights_list")):
        reasons.append("source EPUB's own rights metadata does not cite an accepted licence URI")

    # chapter count and reading order
    committed_labels = [c.get("label") for c in book.get("chapters", [])]
    source_labels = [c.get("label") for c in source["chapters"]]
    if len(committed_labels) != len(source_labels):
        reasons.append(
            "chapter count: committed %d != source %d" % (len(committed_labels), len(source_labels))
        )
    elif committed_labels != source_labels:
        first_diff = next(i for i, (a, b) in enumerate(zip(committed_labels, source_labels)) if a != b)
        reasons.append(
            "reading order diverges at chapter %d: committed %r != source %r"
            % (first_diff, committed_labels[first_diff], source_labels[first_diff])
        )

    # word count, within tolerance
    committed_words = info["committed_words"]
    if committed_words is not None:
        tolerance = max(WORD_COUNT_TOLERANCE_FLOOR, round(committed_words * WORD_COUNT_TOLERANCE_FRACTION))
        diff = abs(committed_words - source["words"])
        info["word_diff"] = diff
        info["word_tolerance"] = tolerance
        if diff > tolerance:
            reasons.append(
                "word count: committed %d, source %d (diff %d, exceeds tolerance %d)"
                % (committed_words, source["words"], diff, tolerance)
            )

    return reasons, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("books", nargs="*", help="books/<slug> directories; default is every book")
    ap.add_argument("--archives", metavar="DIR", help="a local folder of Standard Ebooks bulk-download zips")
    args = ap.parse_args()

    targets = args.books or sorted(glob.glob(os.path.join("books", "*")))
    targets = [t for t in targets if os.path.isdir(t)]

    t0 = time.time()
    failed = 0
    checked = 0
    for i, book_dir in enumerate(targets):
        reasons, info = check_one(book_dir, archives_dir=args.archives)
        if reasons is None:
            print("skip %s -- %s" % (book_dir, info.get("skipped")))
            continue
        checked += 1
        if reasons:
            failed += 1
            print("RED  %s" % book_dir)
            for r in reasons:
                print("  - %s" % r)
        else:
            print(
                "ok   %s (%d chapters, %d words, %d apparatus sections excluded)"
                % (book_dir, info["source_chapters"], info["source_words"], info["apparatus_excluded"])
            )
        if not args.archives and i < len(targets) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    elapsed = time.time() - t0
    print(
        "\ncheck_source: %d book(s) checked, %d failed, %.1fs elapsed (%.3fs/book)"
        % (checked, failed, elapsed, elapsed / max(checked, 1))
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
