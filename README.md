<p align="center">
  <img src="assets/folio.png" width="96" height="96" alt="Folio icon">
</p>

<h1 align="center">Folio</h1>

<p align="center">
  Merge hundreds of PDFs into one complete document, in exactly the order you choose.<br>
  Fast, private, and it runs entirely on your own computer.
</p>

<p align="center">
  <img src="assets/screenshot.jpg" alt="Folio merging the chapters of a book" width="800">
</p>

## Why Folio

Assembling a book from a folder of chapter PDFs shouldn't mean uploading it to a website, fighting a file
limit, or checking 30,000 pages by hand to make sure nothing ended up out of order. Folio is built for exactly
that job.

- **Hundreds of files, any size.** Pages are copied by [qpdf](https://qpdf.readthedocs.io/) without being
  re-rendered, so quality is untouched and large files are fast. A 120-file, 38,000-page, 105 MB book merges, with
  bookmarks, in under 20 seconds on an ordinary laptop.
- **Exactly the order you choose.** Files are sorted naturally (`Chapter 2` before `Chapter 10`), then you drag,
  sort, or use the keyboard to arrange them. What you see is the order you get.
- **Bookmarks for every file.** The merged PDF opens with a clickable table of contents, one entry per file.
- **Page ranges.** Take only the pages you need from any file: `1-5, 8, 12-`.
- **Problems surface early.** Damaged or password-protected files are flagged the moment you add them, never
  silently skipped.
- **Private by design.** Folio is a small local server that only accepts connections from your own computer.
  Nothing is uploaded anywhere, and temporary files are deleted when it closes.

## Getting started

Requires Python 3.10 or newer.

```bash
git clone https://github.com/SylusZephyr/Folio.git
cd Folio
pip install -r requirements.txt
python -m folio
```

Folio opens in its own window (using Edge or Chrome in app mode, or your default browser otherwise) and
shuts down by itself when you close that window.

On Windows you can add it to your Desktop and Start menu:

```bash
python scripts/create_shortcut.py
```

## Using Folio

1. **Add files.** Drop PDFs or whole folders onto the window, or use *Add files* / *Add folder*.
2. **Arrange them.** Drag the ⠿ handle, use *Sort*, or select a row and press <kbd>Alt</kbd>+<kbd>↑</kbd>/<kbd>↓</kbd>.
3. **Optionally choose pages** for any file in the *Pages to include* column.
4. **Merge,** then *Download* or *Preview* the result.

| Shortcut | Action |
| --- | --- |
| <kbd>Ctrl</kbd>+<kbd>O</kbd> | Add files |
| <kbd>↑</kbd> / <kbd>↓</kbd> | Select previous / next file |
| <kbd>Alt</kbd>+<kbd>↑</kbd> / <kbd>↓</kbd> | Move the selected file up / down |
| <kbd>Alt</kbd>+<kbd>Home</kbd> / <kbd>End</kbd> | Move the selected file to the top / bottom |
| <kbd>Delete</kbd> | Remove the selected file |

## Command line

The same engine is available without the window:

```bash
python -m folio.cli -o book.pdf "Chapter 1.pdf" "Chapter 2.pdf"   # files, in this order
python -m folio.cli -o book.pdf --folder chapters                  # whole folder, natural order
python -m folio.cli -o book.pdf --list order.txt                   # one path per line
```

Add `--no-bookmarks` to skip the table of contents. `python -m folio --browser` runs the app in a normal
browser tab instead of its own window.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

The tests cover page ordering across hundreds of files, page ranges, bookmarks, damaged and encrypted
inputs, and the server API, including its protection against requests from other websites.

To try Folio at scale, generate a 120-chapter test book in which every page is stamped with its chapter and
page number, then verify a merge of it:

```bash
python scripts/make_test_book.py
python -m folio.cli -o book.pdf --folder test-book
python scripts/make_test_book.py --check book.pdf
```

### Project layout

```
folio/
  core.py      merge engine: ordering, page ranges, bookmarks
  server.py    local HTTP server and app window
  cli.py       command-line interface
  web/         the interface (HTML, CSS, JavaScript; no build step, no dependencies)
scripts/       shortcut installer, icon renderer, test-book generator
tests/         pytest suite
```

## License

[MIT](LICENSE) © SylusZephyr
