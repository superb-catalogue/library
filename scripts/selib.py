"""Shared reading of Standard Ebooks EPUBs, for the library's ingest scripts.

Everything here reads bytes straight out of the zips — nothing is ever
extracted to disk, and nothing under E:\\archives (or wherever the archives
live) is ever opened for writing.
"""
import hashlib
import re
import xml.etree.ElementTree as ET

OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"


def strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def norm_type(raw):
    """'z3998:letter se:bridge' -> 'letter+bridge' — namespace prefixes are
    the vocabulary's own bookkeeping, not part of the type a reading surface
    would want to switch on."""
    toks = raw.split()
    out = [t.split(":", 1)[1] if ":" in t else t for t in toks]
    return "+".join(out)


def clean_text(s):
    return re.sub(r"[ \t\r\n]+", " ", s).strip()


def text_of(el):
    return "".join(el.itertext())


# The door gate's licence check has to tell a real public-domain dedication
# apart from a restrictive notice that happens to contain the words "public
# domain" — a bare substring test can't, because a rights-reserved notice
# can say "this book is not dedicated to the public domain" and
# still contain the phrase it's being screened for. So this checks for the
# actual dedication language Standard Ebooks uses (or the CC0 deed URL it
# links to) as a genuine positive signal, and rejects outright if any
# explicit restriction marker is present, regardless of what else is in the
# text — a denial always overrides a matched phrase.
_RESTRICTIVE_MARKERS = (
    "all rights reserved",
    "reserves all rights",
    "copyright reserved",
    "may not be reproduced",
    "not be reproduced",
    "without written permission",
    "without permission",
    "without a paid license",
    "without a paid licence",
    "strictly prohibited",
    "reproduction is prohibited",
    "no part of this",
    "not dedicated to the public domain",
    "not in the public domain",
    "not be copied",
)
_DEDICATION_MARKERS = (
    "creativecommons.org/publicdomain/zero",
    "dedicate their contributions to the worldwide public domain",
    "cc0 1.0 universal public domain dedication",
)


def is_genuine_public_domain_dedication(rights_text):
    """True only for text that actually dedicates the work, not text that
    merely mentions the phrase "public domain" somewhere."""
    if not rights_text:
        return False
    t = rights_text.lower()
    if any(marker in t for marker in _RESTRICTIVE_MARKERS):
        return False
    return any(marker in t for marker in _DEDICATION_MARKERS)


def is_standardebooks_identifier(identifier):
    """The identifier has to actually be a Standard Ebooks ebook page — not
    merely present — so a citation someone can resolve for themselves is
    something the gate checked for, not something it assumed."""
    return bool(identifier) and identifier.startswith("https://standardebooks.org/ebooks/")


def find_opf_path(ez):
    container = ez.read("META-INF/container.xml").decode("utf-8")
    m = re.search(r'full-path="([^"]+)"', container)
    if not m:
        raise ValueError("no full-path in META-INF/container.xml")
    return m.group(1)


def parse_metadata(root):
    """Pull the fields the library needs off an OPF <metadata>. Every text
    read here is decoded as UTF-8 upstream by the caller — a mangled
    character on screen is the terminal, not the file (see
    books/HOW-THE-FIRST-BOOK-WENT.md, point 5)."""
    md = root.find("opf:metadata", OPF_NS)

    identifier = None
    for e in md.findall("dc:identifier", OPF_NS):
        identifier = (e.text or "").strip()

    title = None
    for e in md.findall("dc:title", OPF_NS):
        if e.text and e.text.strip():
            title = e.text.strip()
            break

    creators = [(e.text or "").strip() for e in md.findall("dc:creator", OPF_NS) if e.text]

    language = None
    for e in md.findall("dc:language", OPF_NS):
        language = (e.text or "").strip()

    pub_date = None
    for e in md.findall("dc:date", OPF_NS):
        pub_date = (e.text or "").strip()

    rights = None
    for e in md.findall("dc:rights", OPF_NS):
        rights = (e.text or "").strip()

    sources = [(e.text or "").strip() for e in md.findall("dc:source", OPF_NS) if e.text]

    modified = None
    collections = {}
    genres = []
    for e in md.findall("opf:meta", OPF_NS):
        prop = e.get("property")
        if prop == "dcterms:modified":
            modified = (e.text or "").strip()
        elif prop == "schema:genre":
            # Some books carry more than one — e.g. Ashenden is tagged both
            # "Adventure" (what it is) and "Shorts" (a story collection
            # rather than one continuous narrative). Standard Ebooks lists
            # the primary genre first with no other marker distinguishing
            # them, so document order is the only signal; keep all of them
            # and let the caller decide which is the shelf category.
            genres.append((e.text or "").strip())
        elif prop == "belongs-to-collection":
            cid = e.get("id")
            if cid:
                collections.setdefault(cid, {})["name"] = (e.text or "").strip()
        elif prop == "collection-type":
            refid = (e.get("refines") or "").lstrip("#")
            if refid:
                collections.setdefault(refid, {})["type"] = (e.text or "").strip()
        elif prop == "group-position":
            refid = (e.get("refines") or "").lstrip("#")
            if refid:
                collections.setdefault(refid, {})["position"] = (e.text or "").strip()

    return {
        "identifier": identifier,
        "title": title,
        "creators": creators,
        "language": language,
        "date": pub_date,
        "modified": modified,
        "rights": rights,
        "sources": sources,
        "genres": genres,
        "collections": list(collections.values()),
    }


def parse_manifest_spine(root):
    manifest = {}
    for item in root.findall("opf:manifest/opf:item", OPF_NS):
        manifest[item.get("id")] = item.get("href")
    spine = []
    for itemref in root.findall("opf:spine/opf:itemref", OPF_NS):
        idref = itemref.get("idref")
        if idref in manifest:
            spine.append(manifest[idref])
    return spine


def block_of(el):
    """Turn one XHTML element into a block the reading surface can decide
    what to do with, keeping the source's own epub:type rather than
    guessing from a title (books/HOW-THE-FIRST-BOOK-WENT.md, point 2) and
    keeping the letters-and-diary-entries structure a flat list of
    paragraphs would throw away."""
    tag = strip_ns(el.tag)
    epub_type = el.get("{%s}type" % EPUB_NS)

    if tag == "hr":
        return {"type": "break"}
    if tag == "img":
        return None

    if tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
        txt = clean_text(text_of(el))
        if not txt:
            return None
        if epub_type:
            btype = norm_type(epub_type)
        elif tag.startswith("h"):
            btype = "heading"
        elif tag == "li":
            btype = "item"
        else:
            btype = "paragraph"
        return {"type": btype, "text": txt}

    # container-like element (blockquote, div, header, footer, figure,
    # ol, ul, table, nested section) — recurse and keep its own type as
    # the wrapper, so a letter or a diary entry stays a distinguishable
    # group of blocks rather than being flattened into it.
    children = []
    for c in el:
        b = block_of(c)
        if b is not None:
            children.append(b)
    if children:
        btype = norm_type(epub_type) if epub_type else tag
        return {"type": btype, "blocks": children}

    txt = clean_text(text_of(el))
    if txt:
        btype = norm_type(epub_type) if epub_type else tag
        return {"type": btype, "text": txt}
    return None


def extract_chapters(ez, opf_dir, spine_hrefs):
    """Walk the book's own stated reading order (the spine), not filenames
    sorted alphabetically — chapter-10.xhtml sorts right after chapter-1.xhtml
    alphabetically, which is wrong (HOW-THE-FIRST-BOOK-WENT.md, point 1).
    Separate the author's text from the publisher's apparatus using each
    file's own body epub:type (point 2) rather than guessing from titles."""
    chapters = []
    for href in spine_hrefs:
        full = (opf_dir + "/" + href) if opf_dir else href
        full = full.replace("\\", "/")
        try:
            raw = ez.read(full)
        except KeyError:
            continue
        text = raw.decode("utf-8")
        root = ET.fromstring(text)
        body = root.find("{%s}body" % XHTML_NS)
        if body is None:
            continue
        body_type = body.get("{%s}type" % EPUB_NS) or ""
        body_tokens = [t.split(":", 1)[1] if ":" in t else t for t in body_type.split()]
        if "bodymatter" not in body_tokens:
            continue  # frontmatter/backmatter: the publisher's apparatus, not the book

        for child in body:
            ctag = strip_ns(child.tag)
            if ctag not in ("section", "article", "div"):
                continue
            child_type = child.get("{%s}type" % EPUB_NS) or ""
            child_tokens = [t.split(":", 1)[1] if ":" in t else t for t in child_type.split()]

            heading_el = None
            for sub in child.iter():
                if strip_ns(sub.tag) in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    heading_el = sub
                    break
            label = clean_text(text_of(heading_el)) if heading_el is not None else None

            blocks = []
            for sub in child:
                if sub is heading_el:
                    continue
                b = block_of(sub)
                if b is not None:
                    blocks.append(b)

            chapters.append(
                {
                    "href": href,
                    "label": label,
                    "types": body_tokens + child_tokens,
                    "blocks": blocks,
                }
            )
    return chapters


def count_words(chapters):
    total = 0

    def walk(b):
        nonlocal total
        if "text" in b:
            total += len(b["text"].split())
        for c in b.get("blocks", []):
            walk(c)

    for ch in chapters:
        if ch.get("label"):
            total += len(ch["label"].split())
        for b in ch["blocks"]:
            walk(b)
    return total


def slug_from_identifier(identifier):
    """https://standardebooks.org/ebooks/bram-stoker/dracula -> bram-stoker_dracula"""
    m = re.search(r"standardebooks\.org/ebooks/(.+)$", identifier)
    if not m:
        raise ValueError("identifier is not a standardebooks.org ebook page: %r" % identifier)
    return m.group(1).rstrip("/").replace("/", "_")


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()
