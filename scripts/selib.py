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


# What the door gate's licence check does, and just as importantly does
# not, establish. No reading of a file's contents can decide whether
# someone is lying about a licence — a forger can write a flawless CC0
# dedication into a copyrighted book, and no phrase list, regex or Unicode
# normalisation would ever catch that, because the words on the page are
# exactly the words a genuine dedication would use. Two earlier attempts at
# this check tried to make prose carry that weight anyway (a substring
# test, then a longer one), and both were defeated by writing a slightly
# different sentence.
#
# So this checks something a sentence can't fake as cheaply: whether the
# book's own rights metadata cites one of the licence URIs this library
# has agreed to accept. A URI is a structural, machine-readable claim
# rather than prose that happens to be about a licence, and a new licence
# has to be added to the allow-list on purpose, by a person, rather than
# pattern-matched into acceptance by accident.
#
# What this still does and does not prove: it confirms the book SAYS it
# carries a licence this library allows, and that the metadata is there to
# say it. It does not and cannot confirm the claim is true. That is
# verified once, against the book's own public page, when the book is
# chosen for the shelf — the same rule this library already applies to
# every other provenance citation (books/HOW-THE-FIRST-BOOK-WENT.md) — not
# by re-deriving it from the file every time the gate runs. A book from a
# source this library doesn't already trust needs that page-level check
# before it is added; this gate was never a substitute for it and isn't
# built to be one.
ACCEPTED_LICENCE_URIS = (
    "creativecommons.org/publicdomain/zero/1.0",
)

# Phrases that read as restrictive to a human. These are advisory only —
# they never decide whether a book passes the gate, precisely because a
# phrase list is exactly the mechanism that failed twice already. Surface
# them for a person to look at if a book's rights text contains one
# alongside an accepted licence URI; do not act on them automatically.
ADVISORY_RESTRICTIVE_PHRASES = (
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
    "requires a licence from",
    "requires a license from",
)


def licence_uris_in(rights_text):
    """Every accepted licence URI cited in one dc:rights element's text.
    Whitespace is normalised first (clean_text) so a genuine URI that
    happens to wrap across a line break in the source XML isn't missed —
    a check that falsely rejects a real dedication is its own kind of
    broken, not a safer version of a check that falsely accepts one."""
    if not rights_text:
        return []
    t = clean_text(rights_text)
    return [uri for uri in ACCEPTED_LICENCE_URIS if uri in t]


def is_genuine_public_domain_dedication(rights_texts):
    """`rights_texts` is every dc:rights element's text a book carries —
    a book can have more than one, and every one of them has to cite an
    accepted licence URI, not just the last one read, so a restrictive
    statement sitting beside a genuine one in the same metadata can't ride
    along unexamined."""
    if isinstance(rights_texts, str):
        rights_texts = [rights_texts]
    rights_texts = [t for t in (rights_texts or []) if t]
    if not rights_texts:
        return False
    return all(licence_uris_in(t) for t in rights_texts)


def advisory_restrictive_phrases_in(rights_texts):
    """Phrases worth a human's eye — never used to decide the gate. See
    the module-level note above ADVISORY_RESTRICTIVE_PHRASES."""
    if isinstance(rights_texts, str):
        rights_texts = [rights_texts]
    found = []
    for t in rights_texts or []:
        tl = clean_text(t).lower()
        for phrase in ADVISORY_RESTRICTIVE_PHRASES:
            if phrase in tl and phrase not in found:
                found.append(phrase)
    return found


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

    # A book can carry more than one dc:rights element. Every one of them
    # matters to the licence check (see is_genuine_public_domain_dedication),
    # so all of them are kept — not just the last one read.
    rights_list = [(e.text or "").strip() for e in md.findall("dc:rights", OPF_NS) if e.text and e.text.strip()]
    rights = rights_list[-1] if rights_list else None

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
        "rights_list": rights_list,
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
