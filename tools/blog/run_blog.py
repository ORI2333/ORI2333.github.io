from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


QT_BINDINGS = ("PySide6", "PyQt6", "PyQt5")


def has_qt() -> str | None:
    for name in QT_BINDINGS:
        if importlib.util.find_spec(name) is not None:
            return name
    return None


def candidate_pythons() -> list[Path]:
    candidates: list[Path] = [Path(sys.executable)]

    for name in ("python", "pythonw"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(Path(conda_prefix) / "python.exe")
        candidates.append(Path(conda_prefix) / "pythonw.exe")

    common_roots = [
        Path("E:/Program Files/Anaconda"),
        Path("D:/Program Files/Anaconda"),
        Path("C:/ProgramData/anaconda3"),
        Path.home() / "anaconda3",
        Path.home() / "miniconda3",
    ]
    for root in common_roots:
        candidates.append(root / "python.exe")
        candidates.append(root / "pythonw.exe")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key not in seen and path.exists():
            seen.add(key)
            unique.append(path)
    return unique


def detect_qt(python: Path) -> str | None:
    code = (
        "import importlib.util; "
        "mods=['PySide6','PyQt6','PyQt5']; "
        "print(next((m for m in mods if importlib.util.find_spec(m)), ''))"
    )
    try:
        proc = subprocess.run(
            [str(python), "-c", code],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    binding = proc.stdout.strip()
    return binding or None


def find_qt_python() -> tuple[Path, str] | None:
    current_binding = has_qt()
    if current_binding:
        return Path(sys.executable), current_binding

    for python in candidate_pythons():
        binding = detect_qt(python)
        if binding:
            return python, binding
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the blog GUI with a Qt-capable Python.")
    parser.add_argument("--check", action="store_true", help="Print the selected Python and Qt binding, then exit.")
    args = parser.parse_args()

    selected = find_qt_python()
    if not selected:
        print(
            "ERROR: No Python environment with PySide6, PyQt6, or PyQt5 was found.\n"
            "Activate your Anaconda environment first, or install one Qt binding in the Python used by npm.",
            file=sys.stderr,
        )
        return 1

    python, binding = selected
    gui = Path(__file__).resolve().with_name("blog_gui.py")
    if args.check:
        print(f"Python: {python}")
        print(f"Qt binding: {binding}")
        return 0

    if Path(sys.executable).resolve() == python.resolve():
        from blog_gui import main as gui_main

        return gui_main()

    return subprocess.call([str(python), str(gui)])


if __name__ == "__main__":
    raise SystemExit(main())
