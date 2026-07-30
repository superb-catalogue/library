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
  this loses something real, and the next book through should decide what the
  reading surface actually needs before the loss is baked in.
- **Nothing is checked twice yet.** No test says the text in `book.json` matches
  the ebook it came from. That check should exist before there are a thousand of
  these, because after that nobody will read them.
- **One book proves the path exists, not that it scales.** The next few should be
  deliberately awkward: poetry, a play, a collection of short stories, something
  translated.
