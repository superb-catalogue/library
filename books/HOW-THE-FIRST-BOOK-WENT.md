# How the first book went

*Dracula*, taken from a Standard Ebooks edition by hand on 30 July 2026, before
any of this was scripted. Written down because the awkward parts are the spec:
whatever gets automated later has to handle exactly these, and a script written
without doing it once would have guessed wrong on at least three of them.

## What came out

Two files per book, in a folder named for the author and title.

- **`book.json`** — the text, in reading order, as chapters of paragraphs.
  Dracula came to 28 chapters (I–XXVII plus a closing "Note"), 160,112 words,
  845 KB.
- **`provenance.json`** — where it came from, on what terms, and how to check
  that for yourself.

## The five things that were not obvious

**1. Reading order is not alphabetical order, and the file tells you.**
An ebook lists its own reading order. Sorting the chapter files by name puts
chapter 10 immediately after chapter 1. Checked directly on this book: the stated
order and the alphabetical order are **not** the same. Use the stated order.

**2. The book's own tags say what is the book and what is the publisher's
apparatus.** Every section is labelled — front matter, body, back matter. Six
sections here were apparatus: title page, imprint, dedication, preface, half
title, colophon. Those are the publisher's work, not the author's, and they do not
belong in the reading text. **Use the labels, not the titles.** Guessing from
titles is how a preface ends up as chapter one.

**3. Chapter titles are often not titles.** This book's chapters are called "I",
"II", "III". Nothing to show a reader, and no help for finding a place. Whatever
the app puts at the top of a page cannot assume a descriptive name exists.

**4. The licence is in the book, per book, and it is worth reading rather than
assuming.** Each edition states its own terms in its metadata, and this one says
the source text is believed to be in the US public domain and that everyone who
worked on the edition dedicated their own contributions to the public domain under
CC0. There is also a page inside the book making the same statement in plainer
words. **That is the level to check** — a collection saying "these are all free"
is a claim about a bundle; the book saying it is a claim about the book.

**5. A mangled apostrophe in your terminal is probably your terminal.**
Half an hour nearly went into an encoding bug that did not exist: the text printed
with a black diamond where a curly apostrophe should be. The file was correct the
whole time — the console was the thing that could not display it. **Check the
bytes in the file, not the characters on your screen.**

## What provenance records, and why it points where it does

The row cites **the book's own public page** at the publisher, plus the older
editions that one was made from. It deliberately does **not** cite the zip file it
was actually pulled out of, because that file lives on one person's hard drive
behind a membership. A citation only its author can check is not a citation. Anyone
can open the page and compare.

It also records the exact file it came from as a checksum, and the date. That way
"this edition" means one specific file rather than whatever that page serves next
year.

## What is left rough on purpose

- **Only paragraphs survived.** Letters, diary headings, poems and inscriptions
  are all just paragraphs here. Dracula is made of diary entries and letters, so
  this loses something real. Four more books have gone through since, on purpose
  awkward, to see this loss in more shapes — see below — and what it turns into
  is filed as issue #3 on this repository rather than decided here.
- **Nothing was checked twice, until now.** `scripts/check_source.py` verifies a
  committed book against the EPUB it says it came from — chapter count, reading
  order, the excluded publisher apparatus, word count within tolerance, the
  licence dedication, and the identifier. It runs on its own schedule, separate
  from the door gate, and never blocks a book from reaching the shelf.
- **One book proved the path exists. Four more proved it doesn't scale evenly.**
  The next few were meant to be deliberately awkward: poetry, a play, a
  collection of short stories, something translated. All four below.

## Four more books, on purpose awkward

Dracula proved the path exists. It did not prove the path scales, or that
it handles anything other than a Victorian novel told in letters and diary
entries — the next step named in this file was to try shapes on purpose:
poetry, a play, a collection of short stories, something translated. All
four below are on the shelf already, pulled through the automated pipeline
that Dracula's own notes became the spec for. What follows is what a close,
by-hand read of each one — the actual EPUB, not just the output — turned up.

### Poetry: *Leaves of Grass*, Walt Whitman

A poem's lines are marked, and the tools throw the marking away. Standard
Ebooks writes a stanza as one `<p>`, with each line inside its own `<span>`
and a `<br/>` between lines — the line breaks are real markup, not just
visual spacing. `book.json` does not have them. Every block-building
function in this pipeline treats a `<p>` as one unit of text: read
everything inside it, collapse every run of whitespace to a single space,
done. A `<br/>` inside a `<p>` disappears the same way an ordinary space
would. Three lines of "A Song of Joys" —

```
O to make the most jubilant song!
Full of music—full of manhood, womanhood, infancy!
Full of common employments—full of grain and trees.
```

— become one committed block:

```
"O to make the most jubilant song! Full of music—full of manhood,
womanhood, infancy! Full of common employments—full of grain and trees."
```

The chapter itself is correctly typed (`"types": ["bodymatter", "poem"]` —
so a reading surface can tell this is a poem rather than a chapter of
prose), and that is the only place the poem's shape survives. Inside it,
every stanza reads like a run-on sentence. This is the same loss Dracula's
letters and diary headings took, in a different shape: whatever gets built
to hold onto verse lineation has to do it at the line level, not just the
chapter level.

One more thing, small but worth naming exactly because it is small:
Standard Ebooks inserts a zero-width no-break character before certain em
dashes (a typographic word-joiner, so a line never breaks right after a
dash). It is invisible on screen and it is not whitespace, so it survives
into the committed text sitting directly between two words with no visible
gap — "music" and "—full" above are one unbroken run of characters as far
as anything counting words is concerned. It does not corrupt anything
readable, but a word-count or a word-boundary check that assumes whitespace
means a boundary will quietly disagree with what a person sees on the page.

### A play: *Hamlet*, William Shakespeare

Dialogue in Standard Ebooks' plays is an HTML `<table>`: one row per line,
the speaker's name in the first cell, the words in the second. Every block
type this pipeline knows how to name comes from the source's own
`epub:type` attribute — and most of a dialogue table does not carry one.
`<table>`, `<tbody>`, `<tr>`, and the second `<td>` on almost every row are
plain, untyped HTML. The container-handling code, for lack of anything
better, falls back to the raw tag name, so the committed text has blocks
typed `"table"`, `"tbody"`, `"tr"`, `"td"`, and even `"span"` and `"p"` sitting
next to the deliberately-named ones (`"persona"` for a speaker, `"stage-direction"`
for a direction, `"verse"` for a line in verse). A reading surface that
switches on block type has no idea what `"td"` means, because it isn't
content vocabulary at all — it's the table markup the content happened to
be laid out in.

Two more things fell out of reading Act I closely:

- Verse lines spoken as dialogue lose their line breaks exactly the way
  *Leaves of Grass*'s stanzas do, because they are still `<p>` elements
  underneath the table cell. The King's opening speech in Act I, Scene II
  — several lines of blank verse — comes through as one paragraph block,
  same mechanism as above, one level deeper.
- When two characters share a single cue, Standard Ebooks names them
  together in one cell ("Cornelius" and "Voltimand" replying at once). The
  committed text keeps them as one `"persona"` block with both names run
  together — `"Cornelius Voltimand"` — indistinguishable from a single
  character actually named that.

### Short stories: *Short Fiction*, O. Henry

413 stories, each one already its own top-level chapter, each correctly
carrying `"short-story"` in its `types` — the per-story marking is there and
it is right. What isn't there is anywhere the book says, once, "this is a
collection, not one continuous narrative." That fact only exists today as
something you'd notice by reading every chapter's `types` and seeing the
same tag over and over. A reading surface deciding whether "next chapter"
means "continue this story" or "start an unrelated one" — or whether a
reader picking up partway through should land mid-story or at a story's
own beginning — has nothing at the top of `book.json` to ask. The signal is
real; it just lives at the wrong level to be cheap to use.

### Something translated: *Crime and Punishment*, translated by Constance Garnett

This is not a structural loss — it is a name that goes missing. Standard
Ebooks credits Constance Garnett as `<dc:contributor id="translator">`,
with roles marking her as translator, annotator, and preface writer. The
metadata reader this pipeline uses only ever looks at `<dc:creator>` —
which, for a translated work, is the original author alone. `book.json`
and `provenance.json` both say the author is "Fyodor Dostoevsky" and say
nothing else; the translator whose actual sentences make up the English
text a reader sees — the same translator named right there in the book's
own identifier
(`.../ebooks/fyodor-dostoevsky/crime-and-punishment/constance-garnett`) —
isn't recorded anywhere in what gets committed. This isn't specific to this
one book: every translated work on the shelf carries its translator the
same way in its source metadata (`dc:contributor`, role `trl`), so every one
of them is missing that credit today. Filed as issue #4, separate from
issue #3 above, because it is a straightforward gap in what gets read out
of the metadata, not a design question about what the reading surface
needs.

## What the source check (scripts/check_source.py) is, and is not

This check reads a book's *own* committed text back against the EPUB it
was built from — chapter count, reading order, the excluded apparatus,
word count (within a small tolerance, because Standard Ebooks retypesets
books after publication and the public copy this check downloads today can
be a slightly newer build than the one actually ingested), the licence
dedication, and the identifier. It runs against a local archive when one is
given (fast, for a maintainer who has one) or against the book's own public
per-book download otherwise (what the automated run uses — never a patron
zip). It is a separate, slower check, not part of adding a book: it does
not run every time something changes, and it never stands between a book
and the shelf. What it catches is a `book.json` that no longer agrees with
the file it claims to represent — corrupted, hand-edited, or quietly out
of date against a source that has since changed.

