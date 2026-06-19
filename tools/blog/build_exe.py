from __future__ import annotations

import shutil
import subprocess
import sys
import importlib.util
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY = REPO_ROOT / "tools" / "blog" / "run_blog.py"
DIST_ROOT = REPO_ROOT / "dist" / "blog-gui"
QT_BINDINGS = ("PySide6", "PyQt6", "PyQt5")


def main() -> int:
    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        print("ERROR: pyinstaller not found. Install it with: pip install pyinstaller", file=sys.stderr)
        return 1

    detected_qt = next((name for name in QT_BINDINGS if importlib.util.find_spec(name) is not None), None)
    if not detected_qt:
        print("ERROR: no Qt binding found. Install PySide6, PyQt6, or PyQt5 before packaging.", file=sys.stderr)
        return 1
    dist = DIST_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")

    command = [
        pyinstaller,
        "--noconfirm",
        "--windowed",
        "--name",
        "ORI-Blog-Workflow",
        "--distpath",
        str(dist),
        "--workpath",
        str(REPO_ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(REPO_ROOT / "build" / "pyinstaller"),
        "--paths",
        str(REPO_ROOT / "tools" / "blog"),
        "--hidden-import",
        "blog_gui",
        "--hidden-import",
        "blog_core",
        "--hidden-import",
        "blog_cli",
        "--add-data",
        f"{REPO_ROOT / 'tools' / 'blog' / 'blog.config.json'};tools/blog",
        "--add-data",
        f"{REPO_ROOT / 'templates' / 'blog-post.md'};templates",
        str(ENTRY),
    ]
    print("$ " + " ".join(command))
    print(f"Qt binding: {detected_qt}")
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    print(f"Built: {dist / 'ORI-Blog-Workflow' / 'ORI-Blog-Workflow.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
