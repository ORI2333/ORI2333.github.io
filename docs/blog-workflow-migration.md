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
- `tools/blog/build_exe.py` - optional PyInstaller packaging script.
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

4. Launch the GUI and choose the Obsidian vault path in the `路径` section, or update `tools/blog/blog.config.json` directly. You can also set:

```powershell
$env:BLOG_OBSIDIAN_VAULT="D:\path\to\your\vault"
```

5. If Git or npm is not on `PATH`, choose `git.exe` and `npm.cmd` in the GUI `路径` section. The settings are saved as `gitExecutable` and `npmExecutable` in `tools/blog/blog.config.json`.

6. Verify the full workflow environment:

```bash
npm run blog:check
```

Expected output includes Python/Qt, Git, Node.js, npm, Hexo, Obsidian path, and Git status. If something is missing, the report includes a suggested fix.

To only check which Python/Qt runtime will launch the GUI, run:

```text
python tools/blog/run_blog.py --check
```

7. Launch the GUI:

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
npm run blog:build-exe
npm run blog:all
```

## Optional EXE Packaging

The GUI can be packaged with PyInstaller:

```bash
pip install pyinstaller
npm run blog:build-exe
```

The generated executable is a convenience wrapper for the Python GUI. It does not bundle the blog repository, Node.js, npm, Git, or SSH keys. On a new computer you still need:

- the cloned repository,
- `npm ci`,
- Git,
- Node.js,
- an Obsidian vault path configured in the GUI,
- GitHub authentication for pushing the `source` branch if you publish from that computer.

This keeps the executable small and avoids hiding the actual publish chain inside a black box.

Build artifacts are written under a timestamped folder:

```text
dist/blog-gui/YYYYMMDD-HHMMSS/ORI-Blog-Workflow/ORI-Blog-Workflow.exe
```

Timestamped output avoids Windows file-lock problems when a previously packaged exe or DLL is still open.

Recommended usage for the packaged executable:

1. Clone this repository.
2. Put or keep the executable under the repository folder, or start it from the repository root.
3. Click `环境检查`.
4. Use the `路径` panel to choose Obsidian, Git, and npm when the report says they are missing.
5. Run `npm ci` once if the report says `node_modules` or Hexo dependencies are missing.

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

## Cover Rule

`cover` supports local blog paths and image URLs:

```yaml
cover: /images/posts/example-cover.webp
cover: https://example.com/example-cover.webp
```

If `cover` is empty or still uses the placeholder path, sync writes the configured default cover:

```yaml
cover: /images/theme/default-cover.webp
```

In the GUI:

- `选择封面` first asks which article to update, then copies a local image into the blog image folders.
- `封面 URL` first asks which article to update, then writes an `http://` or `https://` image URL.
- You can also write an image URL directly in Obsidian front matter. Sync preserves it.

## Delete Rule

`删除文章` supports searching by title or file name and defaults to the most recently modified posts first. The confirmation shows the Obsidian source path, trash path, and Hexo path. You can either remove only the Hexo copy while keeping the Obsidian source, or move the Obsidian Markdown file into `Blog/Trash`. Both modes remove the same file from Hexo `source/_posts` and run build and publish so the online page is removed.

## Troubleshooting

If `npm run blog` says `No module named PyQt5`, run:

```bash
npm run blog:check
```

If no Qt binding is found, install `PyQt5`, `PyQt6`, or `PySide6` in the Python environment used by the terminal. The packaged exe does not need the external Qt package at runtime because the Qt binding is bundled during packaging.

If Obsidian sync fails, check `tools/blog/blog.config.json` and make sure `obsidianVaultPath` points to an existing vault.

If publishing fails, run:

```bash
git status --short
npm run build
npm run push
```

The normal publish path pushes the `source` branch. GitHub Actions builds and deploys both GitHub Pages and the Hong Kong static host.

## Hong Kong Deploy Secrets

The Hong Kong deploy runs in GitHub Actions with these repository secrets:

```text
HK_HOST=45.192.104.98
HK_PORT=22
HK_USER=root
HK_REMOTE_ROOT=/var/www/ori2333-blog
HK_SSH_KEY=<private key that can SSH to the server>
```

Daily publishing should use `npm run blog` and click `发布全站` or `一键完成`. `npm run blog:deploy-hk` remains available as a local fallback for troubleshooting GitHub Actions or server sync issues.
