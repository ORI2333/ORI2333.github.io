from __future__ import annotations

import json
import os
import re
import shutil
import shlex
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
    obsidian_trash_folder: str
    hexo_posts_folder: str
    hexo_images_folder: str
    post_template_name: str
    default_cover: str
    default_categories: list[str]
    preferred_preview_port: int
    publish_command: str
    hk_deploy_command: str


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
            obsidian_trash_folder=raw.get("obsidianTrashFolder", "Blog/Trash"),
            hexo_posts_folder=raw.get("hexoPostsFolder", "source/_posts"),
            hexo_images_folder=raw.get("hexoImagesFolder", "source/images/posts"),
            post_template_name=raw.get("postTemplateName", "blog-post.md"),
            default_cover=raw.get("defaultCover", "/images/theme/default-cover.webp"),
            default_categories=list(raw.get("defaultCategories", ["docs"])),
            preferred_preview_port=int(raw.get("preferredPreviewPort", 4000)),
            publish_command=raw.get("publishCommand", "npm run push"),
            hk_deploy_command=raw.get("hkDeployCommand", "npm run deploy:hk"),
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
    def obsidian_trash_path(self) -> Path:
        return self.require_vault() / self.config.obsidian_trash_folder

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
            f"Obsidian trash: {self.config.obsidian_trash_folder}",
            f"Hexo posts: {self.config.hexo_posts_folder}",
            f"Hexo images: {self.config.hexo_images_folder}",
            f"Default cover: {self.config.default_cover}",
            f"npm: {self.npm_executable()}",
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

    def latest_obsidian_post(self) -> Path:
        posts = [p for p in self.obsidian_posts_path.glob("*.md") if p.is_file()]
        if not posts:
            raise RuntimeError(f"Obsidian posts folder has no Markdown files: {self.obsidian_posts_path}")
        return max(posts, key=lambda path: path.stat().st_mtime)

    def set_latest_cover_url(self, cover_url: str) -> Path:
        cover_url = cover_url.strip()
        if not cover_url:
            raise ValueError("Cover URL is required.")
        if not re.match(r"^https?://", cover_url, re.IGNORECASE):
            raise ValueError("Cover URL must start with http:// or https://.")
        post = self.latest_obsidian_post()
        self.set_post_cover(post, cover_url)
        return post

    def set_latest_cover_file(self, image_path: Path) -> tuple[Path, str]:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Cover image not found: {image_path}")
        post = self.latest_obsidian_post()
        cover_path = self.copy_cover_image(image_path, post)
        self.set_post_cover(post, cover_path)
        return post, cover_path

    def copy_cover_image(self, image_path: Path, post: Path) -> str:
        self.obsidian_assets_path.mkdir(parents=True, exist_ok=True)
        self.hexo_images_path.mkdir(parents=True, exist_ok=True)
        stem = safe_file_name(post.stem)
        suffix = image_path.suffix.lower() or ".webp"
        file_name = f"{stem}-cover{suffix}"
        obsidian_target = self.obsidian_assets_path / file_name
        hexo_target = self.hexo_images_path / file_name
        shutil.copy2(image_path, obsidian_target)
        shutil.copy2(image_path, hexo_target)
        return f"/images/posts/{file_name}"

    def set_post_cover(self, post: Path, cover_value: str) -> None:
        content = post.read_text(encoding="utf-8-sig")
        updated = set_front_matter_field(content, "cover", cover_value)
        post.write_text(updated, encoding="utf-8")

    def list_obsidian_posts(self) -> list[Path]:
        if not self.obsidian_posts_path.exists():
            return []
        return sorted(
            [post for post in self.obsidian_posts_path.glob("*.md") if post.is_file()],
            key=lambda path: path.name.lower(),
        )

    def delete_post(self, file_name: str) -> tuple[Path, Path | None]:
        source = self.obsidian_posts_path / file_name
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Obsidian post not found: {source}")
        if source.suffix.lower() != ".md":
            raise ValueError(f"Only Markdown posts can be deleted: {source}")

        self.obsidian_trash_path.mkdir(parents=True, exist_ok=True)
        trash_target = self.unique_trash_path(source.name)
        shutil.move(str(source), str(trash_target))

        hexo_target = self.hexo_posts_path / source.name
        removed_hexo: Path | None = None
        if hexo_target.exists() and hexo_target.is_file():
            hexo_target.unlink()
            removed_hexo = hexo_target
        return trash_target, removed_hexo

    def delete_post_and_publish(self, file_name: str, log: LogFn | None = None) -> tuple[Path, Path | None]:
        trash_target, removed_hexo = self.delete_post(file_name)
        if log:
            log(f"已移动到回收站：{trash_target}")
            if removed_hexo:
                log(f"已从 Hexo 删除：{removed_hexo}")
            else:
                log("Hexo 中没有同名文章。")
        self.build(log)
        self.publish_all_targets(log)
        return trash_target, removed_hexo

    def unique_trash_path(self, file_name: str) -> Path:
        target = self.obsidian_trash_path / file_name
        if not target.exists():
            return target
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path(file_name)
        return self.obsidian_trash_path / f"{path.stem}-{stamp}{path.suffix}"

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
                content = normalize_cover(post.read_text(encoding="utf-8-sig"), self.config.default_cover)
                (self.hexo_posts_path / post.name).write_text(content, encoding="utf-8")
                post_count += 1
        elif log:
            log(f"Missing posts folder: {self.obsidian_posts_path}")

        asset_count = copy_folder(self.obsidian_assets_path, self.hexo_images_path, "*", log)
        return post_count, draft_count, asset_count

    def build(self, log: LogFn | None = None) -> None:
        npm = self.npm_executable()
        self.stream_command([npm, "run", "clean"], log)
        self.stream_command([npm, "run", "build"], log)

    def publish(self, log: LogFn | None = None) -> None:
        command = self.resolve_command(self.config.publish_command)
        self.stream_command(command, log)

    def deploy_hk(self, log: LogFn | None = None) -> None:
        command = self.resolve_command(self.config.hk_deploy_command)
        self.stream_command(command, log)

    def publish_all_targets(self, log: LogFn | None = None) -> None:
        if log:
            log("发布源码，GitHub Actions 会自动部署 GitHub Pages 和香港站点。")
        self.publish(log)

    def all(self, log: LogFn | None = None) -> tuple[int, int, int]:
        result = self.sync_to_hexo(log)
        self.build(log)
        self.publish_all_targets(log)
        return result

    def run(self, command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        command = self.resolve_command(command)
        return subprocess.run(
            command,
            cwd=self.repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            shell=False,
            check=check,
        )

    def stream_command(self, command: list[str], log: LogFn | None = None) -> None:
        command = self.resolve_command(command)
        if log:
            log(f"$ {' '.join(command)}")
        proc = subprocess.Popen(
            command,
            cwd=self.repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
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

    def npm_executable(self) -> str:
        found = shutil.which("npm.cmd") or shutil.which("npm")
        if found:
            return found

        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "npm.cmd",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "nodejs" / "npm.cmd",
            Path("E:/Program Files/nodejs/npm.cmd"),
            Path("D:/Program Files/nodejs/npm.cmd"),
            Path("C:/Program Files/nodejs/npm.cmd"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        raise RuntimeError("找不到 npm。请确认 Node.js 已安装，或把 npm.cmd 加入 PATH。")

    def resolve_command(self, command: list[str] | str) -> list[str]:
        if isinstance(command, str):
            command = shlex.split(command, posix=False)
        if command and command[0].lower() == "npm":
            return [self.npm_executable(), *command[1:]]
        return command


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


def normalize_cover(content: str, default_cover: str) -> str:
    match = re.match(r"(?s)^(---\s*\r?\n)(.*?)(\r?\n---)(.*)$", content)
    if not match:
        return content
    front_matter = match.group(2)
    cover_match = re.search(r"(?im)^cover\s*:\s*(.*?)\s*$", front_matter)
    if cover_match:
        value = cover_match.group(1).strip().strip("'\"")
        if value and value != "/images/posts/replace-this-cover.webp":
            return content
    return set_front_matter_field(content, "cover", default_cover)


def set_front_matter_field(content: str, field: str, value: str) -> str:
    match = re.match(r"(?s)^(---\s*\r?\n)(.*?)(\r?\n---)(.*)$", content)
    if not match:
        return f"---\n{field}: {value}\n---\n\n{content}"

    prefix, front_matter, suffix, body = match.groups()
    line = f"{field}: {value}"
    pattern = rf"(?im)^{re.escape(field)}\s*:.*$"
    if re.search(pattern, front_matter):
        front_matter = re.sub(pattern, line, front_matter, count=1)
    else:
        front_matter = f"{front_matter.rstrip()}\n{line}"
    return f"{prefix}{front_matter}{suffix}{body}"


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
