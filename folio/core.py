"""PDF merging engine. Pages are copied by qpdf without re-rendering, so file size and page count don't matter."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pikepdf


class MergeError(Exception):
    """A problem the user can fix (bad file, bad page range). The message is safe to show."""


@dataclass
class Part:
    path: Path
    title: str  # bookmark title
    pages: list[int] | None = None  # 1-based page numbers to take, None = all
    page_count: int | None = None  # total pages in the file, if already known (saves reopening it)


def natural_key(name: str) -> list:
    """Sort key where 'Chapter 2' comes before 'Chapter 10'."""
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", name)]


def parse_ranges(spec: str, page_count: int) -> list[int] | None:
    """Parse '1-5, 8, 10-' into page numbers. Blank means all pages (None). Descending ranges like '5-1' are allowed."""
    spec = spec.strip()
    if not spec:
        return None
    pages = []
    for part in spec.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)(?:\s*-\s*(\d*))?", part)
        if not m:
            raise MergeError(f'"{part}" is not a page or range (use e.g. 1-5, 8, 10-)')
        start = int(m[1])
        end = start if m[2] is None else (int(m[2]) if m[2] else page_count)
        for n in (start, end):
            if not 1 <= n <= page_count:
                raise MergeError(f"page {n} doesn't exist (the file has {page_count} pages)")
        step = 1 if end >= start else -1
        pages.extend(range(start, end + step, step))
    return pages


def page_count(path: Path, display_name: str | None = None) -> int:
    """Open a PDF just enough to count its pages; raises MergeError with a friendly reason if it can't be used."""
    name = display_name or Path(path).name
    try:
        with pikepdf.open(path) as pdf:
            return len(pdf.pages)
    except pikepdf.PasswordError:
        raise MergeError(f"{name} is password-protected") from None
    except Exception:
        raise MergeError(f"{name} is damaged or not a PDF") from None


def _ranges_arg(pages: list[int]) -> str:
    """[1,2,3,7,6] -> '1-3,7-6' so qpdf gets a short argument even for huge selections."""
    runs, start = [], pages[0]
    prev = start
    step = 0
    for n in pages[1:]:
        if step == 0 and abs(n - prev) == 1:
            step = n - prev
        elif n - prev != step or step == 0:
            runs.append((start, prev))
            start, step = n, 0
        prev = n
    runs.append((start, prev))
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def merge(parts: list[Part], out: Path, bookmarks: bool = True, title: str | None = None) -> int:
    """Merge parts into out, in order. Returns the page count of the result."""
    if not parts:
        raise MergeError("nothing to merge")
    counts = [len(p.pages) if p.pages is not None else p.page_count or page_count(p.path, p.title) for p in parts]

    # qpdf's native page merge closes and reopens inputs itself when there are hundreds,
    # so there is no open-file limit to work around. Absolute paths so a name starting
    # with "-" can't be read as an option, and so a numeric name isn't read as a page range.
    args = ["qpdf", "--empty", "--pages"]
    for p in parts:
        args.append(str(Path(p.path).resolve()))
        if p.pages is not None:
            args.append(_ranges_arg(p.pages))
    out = Path(out).resolve()
    raw = out.with_name(out.name + ".part") if bookmarks else out
    args += ["--", str(raw)]
    try:
        pikepdf.Job(args).run()
    except Exception as e:
        raise MergeError(f"merge failed: {e}") from None
    if not bookmarks:
        return sum(counts)

    # second pass: table of contents + document title (pages are copied, not decoded)
    with pikepdf.open(raw) as pdf:
        with pdf.open_outline() as outline:
            offset = 0
            for p, n in zip(parts, counts):
                if n:
                    outline.root.append(pikepdf.OutlineItem(p.title, offset))
                offset += n
        pdf.Root.PageMode = pikepdf.Name.UseOutlines  # open with the bookmarks panel showing
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["dc:title"] = title or out.stem
            meta["xmp:CreatorTool"] = "Folio"
        pdf.save(out)
        total = len(pdf.pages)
    os.remove(raw)
    return total
