"""python -m folio              open Folio in its own window
python -m folio --browser    open in a normal browser tab instead (stop with Ctrl+C)
python -m folio --headless   run the server only, at http://127.0.0.1:8765"""

import sys

from .server import serve

serve(mode="browser" if "--browser" in sys.argv else "headless" if "--headless" in sys.argv else "app")
