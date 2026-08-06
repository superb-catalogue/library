#!/usr/bin/env python3
"""Sync the shelf to a Cloudflare R2 bucket over the S3 API.

    set R2_ACCOUNT_ID=...
    set R2_ACCESS_KEY_ID=...
    set R2_SECRET_ACCESS_KEY=...
    python scripts/upload_r2.py --bucket superb-catalogue --dry-run
    python scripts/upload_r2.py --bucket superb-catalogue

What goes up, and under what keys:

    books/<id>/book.json         the text
    books/<id>/provenance.json   where it came from and on what terms
    books/<id>/glosses.json      the word meanings for that book
    books/INDEX.json             one row per book
    LIBRARY.md, CATEGORIES.md, README.md, NOTICE.md, LICENSE

The same layout the repository uses, so a key is a path and nothing has to
be translated. Credentials are read from the environment and never written
down here.

Re-runs are cheap: an object whose size and MD5 already match what is in the
bucket is skipped, so adding one archive uploads that archive's books rather
than the whole shelf. Pass --force to upload regardless.

Note on what this is and is not. R2 buckets are private, and the S3 endpoint
this writes to is not a public address. Serving the shelf to readers, or
charging crawlers for it, needs a custom domain bound to the bucket, because
Cloudflare's crawler controls work on a zone rather than on an S3 endpoint.
"""
import argparse
import concurrent.futures as futures
import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ["LIBRARY.md", "CATEGORIES.md", "README.md", "NOTICE.md", "LICENSE"]

CONTENT_TYPES = {
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    "": "text/plain; charset=utf-8",
}


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files_to_send() -> list[tuple[Path, str]]:
    """(local path, object key), in the repository's own layout."""
    out: list[tuple[Path, str]] = []
    books = REPO_ROOT / "books"
    for path in sorted(books.rglob("*.json")):
        out.append((path, path.relative_to(REPO_ROOT).as_posix()))
    for name in ROOT_FILES:
        p = REPO_ROOT / name
        if p.is_file():
            out.append((p, name))
    return out


def existing_objects(client, bucket: str) -> dict[str, tuple[int, str]]:
    """key -> (size, etag). One list pass beats a HEAD per object."""
    found: dict[str, tuple[int, str]] = {}
    token = None
    while True:
        kwargs = {"Bucket": bucket, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            found[obj["Key"]] = (obj["Size"], obj["ETag"].strip('"'))
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=os.environ.get("R2_BUCKET", "superb-catalogue"))
    ap.add_argument("--account-id", default=os.environ.get("R2_ACCOUNT_ID"))
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--force", action="store_true", help="upload even when the object already matches")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")

    planned = files_to_send()
    total_bytes = sum(p.stat().st_size for p, _ in planned)
    print(f"{len(planned)} objects, {total_bytes / 1e9:.2f} GB, bucket {args.bucket!r}")

    if args.dry_run and not (key_id and secret and args.account_id):
        for path, key in planned[:5]:
            print(f"  would send {key}")
        print(f"  ... and {max(0, len(planned) - 5)} more")
        print("dry run: no credentials needed, nothing contacted")
        return 0

    missing = [
        name
        for name, value in (
            ("R2_ACCOUNT_ID", args.account_id),
            ("R2_ACCESS_KEY_ID", key_id),
            ("R2_SECRET_ACCESS_KEY", secret),
        )
        if not value
    ]
    if missing:
        print("set these first: " + ", ".join(missing), file=sys.stderr)
        print(
            "R2 keys come from the Cloudflare dashboard: R2, Manage API tokens, "
            "Create API token, Object Read & Write.",
            file=sys.stderr,
        )
        return 2

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{args.account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name="auto",
        config=Config(retries={"max_attempts": 5, "mode": "standard"}),
    )

    print("listing what is already there ...")
    already = {} if args.force else existing_objects(client, args.bucket)
    print(f"  {len(already)} objects already in the bucket")

    todo = []
    for path, key in planned:
        size = path.stat().st_size
        seen = already.get(key)
        # A single-part upload's ETag is the MD5, so it identifies the bytes.
        # Multipart ETags carry a "-N" suffix and are not comparable; those
        # are re-sent rather than guessed at.
        if seen and seen[0] == size and "-" not in seen[1] and seen[1] == md5_of(path):
            continue
        todo.append((path, key))

    print(f"{len(todo)} to send, {len(planned) - len(todo)} already current")
    if args.dry_run:
        for path, key in todo[:10]:
            print(f"  would send {key}")
        print("dry run: nothing uploaded")
        return 0
    if not todo:
        print("bucket is up to date")
        return 0

    sent = 0
    failed: list[tuple[str, str]] = []

    def send(item: tuple[Path, str]) -> None:
        path, key = item
        client.upload_file(
            str(path),
            args.bucket,
            key,
            ExtraArgs={"ContentType": CONTENT_TYPES.get(path.suffix, CONTENT_TYPES[""])},
        )

    with futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        running = {pool.submit(send, item): item for item in todo}
        for done in futures.as_completed(running):
            path, key = running[done]
            try:
                done.result()
                sent += 1
                if sent % 200 == 0 or sent == len(todo):
                    print(f"  {sent}/{len(todo)}")
            except Exception as exc:  # noqa: BLE001 — reported, not swallowed
                failed.append((key, str(exc)))

    print(f"uploaded {sent} object(s)")
    if failed:
        print(f"{len(failed)} failed:", file=sys.stderr)
        for key, why in failed[:20]:
            print(f"  {key}: {why}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
