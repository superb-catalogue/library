#!/usr/bin/env python3
"""Acceptance tests for the door gate's licence check, built as adversarial
files rather than described in a review — this is the check's own memory of
every evasion three separate people had to invent from scratch across three
rounds, so the next one doesn't have to.

    python scripts/test_gate.py

Exits 0 if every case behaves as asserted below, 1 and a printed list of
which case(s) failed otherwise. No archive, network access, or fixture file
is needed — every EPUB here is built in memory from a minimal, valid shape.
"""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest  # noqa: E402
import selib  # noqa: E402

# Standard Ebooks' own, real, public dedication wording — safe to embed
# verbatim (it's their licence text, not book content) and used here as the
# one genuine case everything else is tested against.
GENUINE_SE_RIGHTS = (
    "The source text and artwork in this ebook are believed to be in the "
    "United States public domain. The creators of, and contributors to, "
    "this ebook dedicate their contributions to the worldwide public "
    "domain via the terms in the [CC0 1.0 Universal Public Domain "
    "Dedication](https://creativecommons.org/publicdomain/zero/1.0/)."
)


def build_epub(rights_elements, identifier="https://standardebooks.org/ebooks/test-author/test-book"):
    """A minimal, valid, synthetic EPUB good enough for read_one_epub: one
    bodymatter chapter, one dc:identifier, and however many dc:rights
    elements the caller wants, in the order given."""
    rights_xml = "".join("<dc:rights>%s</dc:rights>" % r for r in rights_elements)
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">%s</dc:identifier>
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:date>2020-01-01T00:00:00Z</dc:date>
    %s
  </metadata>
  <manifest>
    <item id="c1" href="text/chapter-1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>""" % (identifier, rights_xml)

    chapter = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        '<body epub:type="bodymatter"><section epub:type="chapter">'
        "<h2>I</h2><p>Hello.</p></section></body></html>"
    )
    container = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles><rootfile full-path="epub/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles>\n'
        "</container>"
    )

    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    z.writestr("mimetype", "application/epub+zip")
    z.writestr("META-INF/container.xml", container)
    z.writestr("epub/content.opf", opf)
    z.writestr("epub/text/chapter-1.xhtml", chapter)
    z.close()
    return buf.getvalue()


def gate_result(name, data):
    """Runs the real read_one_epub()/gate() pipeline, the same functions
    scripts/ingest.py's actual add path uses — never a reimplementation of
    the check's logic. A raise counts as passed=False."""
    try:
        rec = ingest.read_one_epub("test", name, data)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), []
    return ingest.gate(rec)


CASES = [
    # (name, rights_elements, expect_pass, identifier_override)
    ("genuine Standard Ebooks dedication, single element", [GENUINE_SE_RIGHTS], True, None),
    ("no dc:rights element at all", [], False, None),
    (
        "hostile host carrying the accepted URI as a path segment",
        [
            "This ebook is licensed for personal use only; redistribution is "
            "prohibited except as permitted at "
            "https://evil.example.com/creativecommons.org/publicdomain/zero/1.0/ "
            "under our own separate terms."
        ],
        False,
        None,
    ),
    (
        "lookalike host: creativecommons.org.evil.com",
        ["Dedicated at https://creativecommons.org.evil.com/publicdomain/zero/1.0/"],
        False,
        None,
    ),
    (
        "lookalike host, wrong TLD: creativecommons.com",
        ["Dedicated at https://creativecommons.com/publicdomain/zero/1.0/"],
        False,
        None,
    ),
    (
        "a different, restrictive CC licence only (BY-NC-ND)",
        ["Licensed under https://creativecommons.org/licenses/by-nc-nd/4.0/"],
        False,
        None,
    ),
    (
        "accepted URI beside a disallowed licence URI in the same element",
        [GENUINE_SE_RIGHTS + " The publisher's preferred terms are "
         "https://creativecommons.org/licenses/by-nc-nd/4.0/."],
        False,
        None,
    ),
    (
        "restrictive phrase beside a valid accepted URI — must PASS, and must be advisory-flagged",
        ["All rights reserved. " + GENUINE_SE_RIGHTS],
        True,
        None,
    ),
    (
        "two dc:rights elements: restrictive first, genuine last",
        ["All rights reserved. No part of this may be reproduced.", GENUINE_SE_RIGHTS],
        False,
        None,
    ),
    (
        "two dc:rights elements: genuine first, restrictive last",
        [GENUINE_SE_RIGHTS, "All rights reserved. No part of this may be reproduced."],
        False,
        None,
    ),
    (
        "http scheme, no trailing slash — same licence, must still pass",
        ["Dedicated at http://creativecommons.org/publicdomain/zero/1.0"],
        True,
        None,
    ),
    (
        "case-folded host and path — same licence, must still pass",
        ["Dedicated at https://CreativeCommons.ORG/publicdomain/zero/1.0/"],
        True,
        None,
    ),
    (
        "percent-encoded host — rejected rather than normalised",
        ["Dedicated at https://creative%63ommons.org/publicdomain/zero/1.0/"],
        False,
        None,
    ),
    (
        "genuine dedication wrapped across an internal line break — must still pass",
        [
            "The source text and artwork in this ebook are believed to be in the\n"
            "United States public domain. The creators of, and contributors to,\n"
            "this ebook dedicate their contributions to the worldwide public\n"
            "domain via the terms in the CC0 1.0 Universal Public Domain\n"
            "Dedication (https://creativecommons.org/publicdomain/zero/1.0/)."
        ],
        True,
        None,
    ),
    (
        "identifier is well-formed but not a standardebooks.org page",
        [GENUINE_SE_RIGHTS],
        False,
        "https://example.com/not-standard-ebooks",
    ),
]


def run():
    failures = []
    for name, rights_elements, expect_pass, identifier_override in CASES:
        kwargs = {"identifier": identifier_override} if identifier_override else {}
        data = build_epub(rights_elements, **kwargs)
        passed, reason, advisory = gate_result(name, data)
        ok = passed == expect_pass
        print(
            "%-4s %-75s passed=%-5s (expected %-5s) reason=%s%s"
            % ("ok" if ok else "FAIL", name, passed, expect_pass, reason, (" advisory=%r" % advisory) if advisory else "")
        )
        if not ok:
            failures.append(name)

    # The advisory list must actually fire for the case that names it, not
    # merely exist as a correctly-written, uncalled function (round 3's
    # Finding 12).
    advisory_data = build_epub(["All rights reserved. " + GENUINE_SE_RIGHTS])
    passed, reason, advisory = gate_result("advisory must fire", advisory_data)
    if not advisory:
        print("FAIL advisory list is empty for a restrictive phrase beside a valid URI")
        failures.append("advisory must fire")
    else:
        print("ok   advisory fired: %r" % advisory)

    print()
    if failures:
        print("%d case(s) failed: %s" % (len(failures), failures))
        return 1
    print("all %d case(s) passed" % (len(CASES) + 1))
    return 0


if __name__ == "__main__":
    sys.exit(run())
