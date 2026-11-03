"""Build a portable Windows x64 ZIP using the official CPython embedded runtime.

Run with Python 3.10+ on any platform. Only allowlisted application files are
copied; local journals, settings, credentials and saved state are never bundled.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.13.17"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
# Published at https://www.python.org/downloads/release/python-31317/
PYTHON_SHA256 = "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38"


def build(output, runtime_zip=None):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="elitelab-bundle-") as temporary:
        staging = Path(temporary)
        archive = staging / "python.zip"
        if runtime_zip:
            shutil.copyfile(runtime_zip, archive)
        else:
            print(f"Downloading {PYTHON_URL}", flush=True)
            with urllib.request.urlopen(PYTHON_URL, timeout=120) as response, archive.open("wb") as target:
                shutil.copyfileobj(response, target)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != PYTHON_SHA256:
            raise ValueError("Python runtime checksum mismatch; bundle was not built")

        app = staging / "EliteLab"
        runtime = app / "runtime"
        with zipfile.ZipFile(archive) as package:
            package.extractall(runtime)
        # Embedded Python ignores PATH/PYTHONPATH and does not add the working
        # directory. Add the application root explicitly; retain isolation.
        (runtime / "python313._pth").write_text("python313.zip\n.\n..\n", encoding="ascii")
        for folder in ("elitelab", "modules", "web"):
            shutil.copytree(ROOT / folder, app / folder,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"))
        for name in ("Start EliteLab.cmd", "Setup EliteLab.cmd", "README.md", "LICENSE"):
            shutil.copyfile(ROOT / name, app / name)
        (app / ".windows-bundle").write_text("Windows portable bundle\n", encoding="ascii")
        (app / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts" / "serve-loop.cmd", app / "scripts" / "serve-loop.cmd")
        (app / "START HERE.txt").write_text(
            "EliteLab for Windows x64\n\n"
            "1. Extract the entire ZIP to a folder you can write to.\n"
            "2. Double-click Setup EliteLab.cmd on first use. Python is included.\n"
            "3. Leave the terminal open while using EliteLab. Ctrl+C stops it.\n\n"
            "Choose journals in setup, Save, then Restart if requested.\n"
            "Next time, double-click Start EliteLab.cmd.\n"
            "The dashboard opens as an app window when a supported browser is present.\n"
            "If the browser does not open, use the URL printed in the terminal.\n"
            "Startup errors stay visible in the terminal.\n"
            "Your own journals are detected in Saved Games. Local settings and\n"
            "trade state default to LocalAppData/EliteLab/data; settings live in\n"
            "AppData/EliteLab. Existing data folders beside the app still work.\n"
            "When updating an older bundle to a new folder, select the old data\n"
            "folder in setup or copy it to LocalAppData/EliteLab/data first.\n\n"
            f"Includes CPython {PYTHON_VERSION}; see runtime/LICENSE.txt.\n",
            encoding="ascii")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(app.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(staging))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Built {output} ({output.stat().st_size / 1024 / 1024:.1f} MiB)")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "EliteLab-windows-x64.zip")
    parser.add_argument("--runtime-zip", type=Path, help="use a cached runtime ZIP (checksum still verified)")
    args = parser.parse_args()
    build(args.output, args.runtime_zip)
