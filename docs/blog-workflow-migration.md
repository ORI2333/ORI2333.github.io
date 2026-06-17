# Blog Workflow Migration

This note explains how to restore the local blog workflow on a new computer or after switching Python environments.

## What This Workflow Uses

- Node.js and npm for Hexo.
- Git for source publishing.
- Python for the blog helper.
- One Qt binding for the GUI: `PySide6`, `PyQt6`, or `PyQt5`.
- Obsidian as the drafting workspace.

## Important Files

- `tools/blog/run_blog.py` - finds a Qt-capable Python and launches the GUI.
- `tools/blog/blog_gui.py` - GUI.
- `tools/blog/blog_cli.py` - command line actions.
- `tools/blog/blog_core.py` - shared sync/build/publish logic.
- `tools/blog/blog.config.json` - local path and workflow config.
- `templates/blog-post.md` - post template.
- `.codex/skills/blog-workflow/SKILL.md` - Codex workflow instructions.

## New Computer Setup

1. Clone the repository and install Node dependencies:

```bash
npm ci
```

2. Install or activate a Python environment with one Qt binding:

```bash
python -c "import PyQt5"
```

Any one of these is fine:

```bash
pip install PyQt5
pip install PyQt6
pip install PySide6
```

If using Anaconda, install into the environment used by the repo terminal:

```bash
conda install pyqt
```

3. Restore or create the Obsidian folders:

```text
Blog/
  Posts/
  Assets/
  Templates/
```

4. Update the vault path in `tools/blog/blog.config.json`, or set:

```powershell
$env:BLOG_OBSIDIAN_VAULT="D:\path\to\your\vault"
```

5. Verify the GUI environment:

```bash
npm run blog:check
```

Expected output includes a Python path and a Qt binding, for example:

```text
Python: E:\Program Files\Anaconda\python.exe
Qt binding: PyQt5
```

6. Launch the GUI:

```bash
npm run blog
```

## Daily Commands

```bash
npm run blog
npm run blog:status
npm run blog:new
npm run blog:sync
npm run blog:build
npm run blog:preview
npm run blog:publish
npm run blog:all
```

## Draft Rule

New Obsidian posts use:

```yaml
draft: true
```

`Sync` skips these private drafts. To publish a post, change it to:

```yaml
draft: false
```

or remove the `draft` line.

## Troubleshooting

If `npm run blog` says `No module named PyQt5`, run:

```bash
npm run blog:check
```

If no Qt binding is found, install `PyQt5`, `PyQt6`, or `PySide6` in the Python environment used by the terminal.

If Obsidian sync fails, check `tools/blog/blog.config.json` and make sure `obsidianVaultPath` points to an existing vault.

If publishing fails, run:

```bash
git status --short
npm run build
npm run push
```

The normal publish path pushes the `source` branch. GitHub Actions builds and deploys the static site.
