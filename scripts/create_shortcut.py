"""Windows: add Folio to the Desktop and Start menu, so it opens like any other app."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if sys.platform != "win32":
        sys.exit("Shortcuts are Windows-only. Elsewhere, run: python -m folio")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(shutil.which("pythonw") or sys.executable)
    ps = f"""
    $shell = New-Object -ComObject WScript.Shell
    foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
        $s = $shell.CreateShortcut((Join-Path $dir 'Folio.lnk'))
        $s.TargetPath = '{pythonw}'
        $s.Arguments = '"{ROOT / "Folio.pyw"}"'
        $s.WorkingDirectory = '{ROOT}'
        $s.IconLocation = '{ROOT / "assets" / "folio.ico"}'
        $s.Description = 'Merge PDFs in the exact order you choose'
        $s.Save()
    }}
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print("Folio added to your Desktop and Start menu.")


if __name__ == "__main__":
    main()
