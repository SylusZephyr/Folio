"""Command-line merging.

  python -m folio.cli -o book.pdf a.pdf b.pdf c.pdf     # files, in this order
  python -m folio.cli -o book.pdf --list order.txt      # one path per line, in this order
  python -m folio.cli -o book.pdf --folder chapters     # natural filename order (2 before 10)
"""

import argparse
import sys
import time
from pathlib import Path

from .core import MergeError, Part, merge, natural_key


def main(argv=None):
    ap = argparse.ArgumentParser(prog="folio", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help="PDF files, merged in the order given")
    ap.add_argument("-o", "--output", required=True, type=Path)
    ap.add_argument("--list", type=Path, help="text file with one PDF path per line")
    ap.add_argument("--folder", type=Path, help="folder of PDFs, natural filename order")
    ap.add_argument("--no-bookmarks", action="store_true", help="don't add a bookmark for each file")
    a = ap.parse_args(argv)

    paths = list(a.files)
    if a.list:
        lines = a.list.read_text(encoding="utf-8-sig").splitlines()
        paths += [Path(line.strip().strip('"')) for line in lines if line.strip()]
    if a.folder:
        paths += sorted(a.folder.glob("*.pdf"), key=lambda p: natural_key(p.name))
    if not paths:
        ap.error("no input PDFs")

    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        sys.exit("error: missing files:\n  " + "\n  ".join(missing))
    out = a.output.resolve()
    if out in {p.resolve() for p in paths}:
        sys.exit("error: the output file is also an input")

    start = time.perf_counter()
    try:
        pages = merge([Part(p, p.stem) for p in paths], out, bookmarks=not a.no_bookmarks)
    except MergeError as e:
        sys.exit(f"error: {e}")
    print(f"Merged {len(paths)} PDFs ({pages:,} pages) into {out} in {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
