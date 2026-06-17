from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable


LogFn = Callable[[str], None]


@dataclass
class BlogConfig:
    obsidian_vault_path: Path
    obsidian_posts_folder: str
    obsidian_assets_folder: str
    hexo_posts_folder: str
    hexo_images_folder: str
    post_template_name: str
    default_categories: list[str]
    preferred_preview_port: int
    publish_command: str


class BlogWorkflow:
    def __init__(self, repo_root: Path | None = None, config_path: Path | None = None):
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.tool_root = Path(__file__).resolve().parent
        self.config_path = config_path or self.tool_root / "blog.config.json"
        self.config = self.load_config()

    def load_config(self) -> BlogConfig:
        raw = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        vault = os.environ.get("BLOG_OBSIDIAN_VAULT") or raw.get("obsidianVaultPath", "")
        return BlogConfig(
            obsidian_vault_path=Path(vault) if vault else Path(),
            obsidian_posts_folder=raw.get("obsidianPostsFolder", "Blog/Posts"),
            obsidian_assets_folder=raw.get("obsidianAssetsFolder", "Blog/Assets"),
            hexo_posts_folder=raw.get("hexoPostsFolder", "source/_posts"),
            hexo_images_folder=raw.get("hexoImagesFolder", "source/images/posts"),
            post_template_name=raw.get("postTemplateName", "blog-post.md"),
            default_categories=list(raw.get("defaultCategories", ["docs"])),
            preferred_preview_port=int(raw.get("preferredPreviewPort", 4000)),
            publish_command=raw.get("publishCommand", "npm run push"),
        )

    @property
    def template_path(self) -> Path:
        return self.repo_root / "templates" / self.config.post_template_name

    @property
    def obsidian_posts_path(self) -> Path:
        return self.require_vault() / self.config.obsidian_posts_folder

    @property
    def obsidian_assets_path(self) -> Path:
        return self.require_vault() / self.config.obsidian_assets_folder

    @property
    def hexo_posts_path(self) -> Path:
        return self.repo_root / self.config.hexo_posts_folder

    @property
    def hexo_images_path(self) -> Path:
        return self.repo_root / self.config.hexo_images_folder

    def require_vault(self) -> Path:
        vault = self.config.obsidian_vault_path
        if not str(vault):
            raise RuntimeError("Set obsidianVaultPath in tools/blog/blog.config.json or BLOG_OBSIDIAN_VAULT.")
        if not vault.exists():
            raise RuntimeError(f"Obsidian vault not found: {vault}")
        return vault

    def status_lines(self) -> list[str]:
        try:
            vault = str(self.require_vault())
        except RuntimeError:
            vault = "<not configured>"
        lines = [
            f"Repo root: {self.repo_root}",
            f"Vault: {vault}",
            f"Obsidian posts: {self.config.obsidian_posts_folder}",
            f"Obsidian assets: {self.config.obsidian_assets_folder}",
            f"Hexo posts: {self.config.hexo_posts_folder}",
            f"Hexo images: {self.config.hexo_images_folder}",
        ]
        proc = self.run(["git", "status", "--short"], check=False)
        if proc.stdout.strip():
            lines.append("")
            lines.extend(proc.stdout.rstrip().splitlines())
        if proc.stderr.strip():
            lines.append("")
            lines.extend(proc.stderr.rstrip().splitlines())
        return lines

    def create_post(self, title: str, open_after: bool = False) -> Path:
        title = title.strip()
        if not title:
            raise ValueError("Post title is required.")
        post_dir = self.obsidian_posts_path
        post_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        file_name = f"{now:%Y-%m-%d}-{safe_file_name(title)}.md"
        target = post_dir / file_name
        if target.exists():
            raise FileExistsError(f"File already exists: {target}")

        template = self.template_path.read_text(encoding="utf-8-sig")
        content = (
            template.replace("{{title}}", yaml_scalar(title))
            .replace("{{date}}", yaml_scalar(now.strftime("%Y-%m-%d %H:%M:%S")))
        )
        target.write_text(content, encoding="utf-8")
        if open_after:
            open_path(target)
        return target

    def import_to_obsidian(self, log: LogFn | None = None) -> tuple[int, int]:
        post_count = copy_folder(self.hexo_posts_path, self.obsidian_posts_path, "*.md", log)
        asset_count = copy_folder(self.hexo_images_path, self.obsidian_assets_path, "*", log)
        return post_count, asset_count

    def sync_to_hexo(self, log: LogFn | None = None) -> tuple[int, int, int]:
        self.hexo_posts_path.mkdir(parents=True, exist_ok=True)
        self.hexo_images_path.mkdir(parents=True, exist_ok=True)

        post_count = 0
        draft_count = 0
        if self.obsidian_posts_path.exists():
            for post in sorted(self.obsidian_posts_path.glob("*.md")):
                if is_draft_post(post):
                    draft_count += 1
                    continue
                shutil.copy2(post, self.hexo_posts_path / post.name)
                post_count += 1
        elif log:
            log(f"Missing posts folder: {self.obsidian_posts_path}")

        asset_count = copy_folder(self.obsidian_assets_path, self.hexo_images_path, "*", log)
        return post_count, draft_count, asset_count

    def build(self, log: LogFn | None = None) -> None:
        self.stream_command(["npm", "run", "clean"], log)
        self.stream_command(["npm", "run", "build"], log)

    def publish(self, log: LogFn | None = None) -> None:
        command = self.config.publish_command.split()
        self.stream_command(command, log)

    def all(self, log: LogFn | None = None) -> tuple[int, int, int]:
        result = self.sync_to_hexo(log)
        self.build(log)
        self.publish(log)
        return result

    def run(self, command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            shell=False,
            check=check,
        )

    def stream_command(self, command: list[str], log: LogFn | None = None) -> None:
        if log:
            log(f"$ {' '.join(command)}")
        proc = subprocess.Popen(
            command,
            cwd=self.repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if log:
                log(line.rstrip())
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"Command failed with exit code {code}: {' '.join(command)}")


def yaml_scalar(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def safe_file_name(value: str) -> str:
    name = value.strip()
    for char in '<>:"/\\|?*':
        name = name.replace(char, "-")
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or "untitled"


def is_draft_post(path: Path) -> bool:
    content = path.read_text(encoding="utf-8-sig")
    match = re.match(r"(?s)^---\s*\r?\n(.*?)\r?\n---", content)
    if not match:
        return False
    return re.search(r"(?im)^\s*draft\s*:\s*true\s*$", match.group(1)) is not None


def copy_folder(source: Path, destination: Path, pattern: str, log: LogFn | None = None) -> int:
    if not source.exists():
        if log:
            log(f"Skip missing folder: {source}")
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in source.rglob(pattern):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        count += 1
    return count


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def iter_lines(lines: Iterable[str]) -> str:
    return "\n".join(lines)
