from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable


LogFn = Callable[[str], None]


DEFAULT_CONFIG = {
    "obsidianVaultPath": "",
    "obsidianPostsFolder": "Blog/Posts",
    "obsidianAssetsFolder": "Blog/Assets",
    "obsidianTrashFolder": "Blog/Trash",
    "gitExecutable": "git",
    "npmExecutable": "",
    "hexoPostsFolder": "source/_posts",
    "hexoImagesFolder": "source/images/posts",
    "postTemplateName": "blog-post.md",
    "defaultCover": "/images/theme/default-cover.webp",
    "defaultCategories": ["docs"],
    "preferredPreviewPort": 4000,
    "publishCommand": "npm run push",
    "hkDeployCommand": "npm run deploy:hk",
}


@dataclass
class BlogConfig:
    obsidian_vault_path: Path
    obsidian_posts_folder: str
    obsidian_assets_folder: str
    obsidian_trash_folder: str
    git_executable: str
    npm_executable_path: str
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
        self.repo_root = repo_root or discover_repo_root()
        self.tool_root = self.repo_root / "tools" / "blog"
        self.config_path = config_path or self.tool_root / "blog.config.json"
        self.config = self.load_config()

    def load_config(self) -> BlogConfig:
        raw = dict(DEFAULT_CONFIG)
        if self.config_path.exists():
            raw.update(json.loads(self.config_path.read_text(encoding="utf-8-sig")))
        vault = os.environ.get("BLOG_OBSIDIAN_VAULT") or raw.get("obsidianVaultPath", "")
        return BlogConfig(
            obsidian_vault_path=Path(vault) if vault else Path(),
            obsidian_posts_folder=raw.get("obsidianPostsFolder", "Blog/Posts"),
            obsidian_assets_folder=raw.get("obsidianAssetsFolder", "Blog/Assets"),
            obsidian_trash_folder=raw.get("obsidianTrashFolder", "Blog/Trash"),
            git_executable=raw.get("gitExecutable", "git"),
            npm_executable_path=raw.get("npmExecutable", ""),
            hexo_posts_folder=raw.get("hexoPostsFolder", "source/_posts"),
            hexo_images_folder=raw.get("hexoImagesFolder", "source/images/posts"),
            post_template_name=raw.get("postTemplateName", "blog-post.md"),
            default_cover=raw.get("defaultCover", "/images/theme/default-cover.webp"),
            default_categories=list(raw.get("defaultCategories", ["docs"])),
            preferred_preview_port=int(raw.get("preferredPreviewPort", 4000)),
            publish_command=raw.get("publishCommand", "npm run push"),
            hk_deploy_command=raw.get("hkDeployCommand", "npm run deploy:hk"),
        )

    def update_config(self, **updates: str) -> None:
        raw = dict(DEFAULT_CONFIG)
        if self.config_path.exists():
            raw.update(json.loads(self.config_path.read_text(encoding="utf-8-sig")))
        raw.update(updates)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.config = self.load_config()

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
            f"git: {self.git_executable()}",
        ]
        for label, command in (
            ("git version", [self.git_executable(), "--version"]),
            ("npm version", [self.npm_executable(), "--version"]),
        ):
            version_proc = self.run(command, check=False)
            value = (version_proc.stdout or version_proc.stderr).strip()
            if value:
                lines.append(f"{label}: {value}")
        proc = self.run([self.git_executable(), "status", "--short"], check=False)
        if proc.stdout.strip():
            lines.append("")
            lines.extend(proc.stdout.rstrip().splitlines())
        if proc.stderr.strip():
            lines.append("")
            lines.extend(proc.stderr.rstrip().splitlines())
        return lines

    def environment_report(self) -> list[str]:
        lines = [
            "博客工作流环境检查",
            f"检查时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
        ]
        vault = self.config.obsidian_vault_path
        obsidian_posts = vault / self.config.obsidian_posts_folder if str(vault) else Path()
        obsidian_assets = vault / self.config.obsidian_assets_folder if str(vault) else Path()
        checks = [
            self.check_python(),
            self.check_qt(),
            self.check_path("博客仓库", self.repo_root, "请把 exe 放在仓库内运行，或从仓库根目录启动。"),
            self.check_path("package.json", self.repo_root / "package.json", "当前目录不像 Hexo 博客仓库。"),
            self.check_path(".git", self.repo_root / ".git", "请先 clone 博客源码仓库。"),
            self.check_path("Obsidian 库", vault, "在 GUI 的“路径”区域选择 Obsidian 库。"),
            self.check_path(
                "Obsidian 文章目录",
                obsidian_posts,
                "首次使用可在 Obsidian 库内创建 Blog/Posts，或点击“导入到 Obsidian”。",
            ),
            self.check_path(
                "Obsidian 资源目录",
                obsidian_assets,
                "首次使用可在 Obsidian 库内创建 Blog/Assets。",
            ),
            self.check_path("Hexo 文章目录", self.hexo_posts_path, "请确认仓库完整，或运行 npm ci 后重试。"),
            self.check_path("Node 依赖", self.repo_root / "node_modules", "请在仓库根目录运行 npm ci。"),
            self.check_command("Git", lambda: [self.git_executable(), "--version"], "安装 Git for Windows：https://git-scm.com/download/win，或在 GUI 里选择 git.exe。"),
            self.check_command("Node.js", lambda: [self.node_executable(), "--version"], "安装 Node.js LTS：https://nodejs.org/。"),
            self.check_command("npm", lambda: [self.npm_executable(), "--version"], "Node.js 安装后应自带 npm；如未找到，请检查 PATH 或在配置里填写 npmExecutable。"),
            self.check_command("Hexo", lambda: [self.npm_executable(), "exec", "hexo", "--", "version"], "请先运行 npm ci 安装博客依赖。"),
        ]

        ok_count = sum(1 for check in checks if check[0] == "OK")
        warn_count = sum(1 for check in checks if check[0] == "WARN")
        missing_count = sum(1 for check in checks if check[0] == "MISS")
        lines.append(f"摘要：正常 {ok_count} 项，提醒 {warn_count} 项，缺失 {missing_count} 项")
        lines.append("")
        for status, label, detail, guidance in checks:
            mark = {"OK": "[正常]", "WARN": "[提醒]", "MISS": "[缺失]"}.get(status, "[信息]")
            lines.append(f"{mark} {label}：{detail}")
            if guidance:
                lines.append(f"  处理建议：{guidance}")

        lines.extend(["", "Git 状态："])
        git_status = self.git_status_summary()
        lines.extend(f"  {line}" for line in git_status)
        return lines

    def check_path(self, label: str, path: Path, guidance: str) -> tuple[str, str, str, str]:
        if not str(path):
            return ("MISS", label, "未配置", guidance)
        if path.exists():
            return ("OK", label, str(path), "")
        return ("MISS", label, f"不存在：{path}", guidance)

    def check_python(self) -> tuple[str, str, str, str]:
        detail = f"{sys.version.split()[0]} ({sys.executable})"
        if getattr(sys, "frozen", False):
            detail = f"exe 内置运行时 ({sys.executable})"
        return ("OK", "Python/GUI 运行时", detail, "")

    def check_qt(self) -> tuple[str, str, str, str]:
        for name in ("PySide6", "PyQt6", "PyQt5"):
            if importlib.util.find_spec(name) is not None:
                return ("OK", "Qt 图形界面", name, "")
        return (
            "MISS",
            "Qt 图形界面",
            "未找到 PySide6 / PyQt6 / PyQt5",
            "如果不用 exe，请在当前 Python 环境安装 PySide6、PyQt6 或 PyQt5；Anaconda 可用 conda install pyqt。",
        )

    def check_command(
        self,
        label: str,
        command_factory: Callable[[], list[str]],
        guidance: str,
    ) -> tuple[str, str, str, str]:
        try:
            command = command_factory()
            proc = subprocess.run(
                command,
                cwd=self.repo_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=20,
                shell=False,
                check=False,
            )
        except Exception as exc:
            return ("MISS", label, str(exc), guidance)
        output = strip_ansi((proc.stdout or proc.stderr).strip())
        output_lines = [line.strip() for line in output.splitlines() if line.strip()]
        useful_lines = [line for line in output_lines if not line.startswith("INFO ")]
        first_line = (useful_lines or output_lines or [f"退出码 {proc.returncode}"])[0]
        if proc.returncode == 0:
            return ("OK", label, first_line, "")
        return ("WARN", label, first_line, guidance)

    def git_status_summary(self) -> list[str]:
        try:
            branch_proc = self.run([self.git_executable(), "branch", "--show-current"], check=False)
            status_proc = self.run([self.git_executable(), "status", "--short"], check=False)
            remote_proc = self.run([self.git_executable(), "remote", "-v"], check=False)
        except Exception as exc:
            return [f"无法读取 Git 状态：{exc}"]

        lines: list[str] = []
        branch = branch_proc.stdout.strip() or "<未知分支>"
        lines.append(f"当前分支：{branch}")
        status = status_proc.stdout.strip()
        if status:
            lines.append("有未提交变更：")
            lines.extend(f"    {line}" for line in status.splitlines())
        else:
            lines.append("工作区干净。")
        remote = remote_proc.stdout.strip()
        if remote:
            lines.append("远程仓库：")
            lines.extend(f"    {line}" for line in remote.splitlines())
        elif remote_proc.stderr.strip():
            lines.append(f"远程仓库读取失败：{remote_proc.stderr.strip()}")
        else:
            lines.append("未配置远程仓库。")
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
        post = self.latest_obsidian_post()
        self.set_post_cover_url(post.name, cover_url)
        return post

    def set_post_cover_url(self, file_name: str, cover_url: str) -> Path:
        cover_url = cover_url.strip()
        if not cover_url:
            raise ValueError("Cover URL is required.")
        if not re.match(r"^https?://", cover_url, re.IGNORECASE):
            raise ValueError("Cover URL must start with http:// or https://.")
        post = self.obsidian_post(file_name)
        self.set_post_cover(post, cover_url)
        return post

    def set_latest_cover_file(self, image_path: Path) -> tuple[Path, str]:
        post = self.latest_obsidian_post()
        return self.set_post_cover_file(post.name, image_path)

    def set_post_cover_file(self, file_name: str, image_path: Path) -> tuple[Path, str]:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Cover image not found: {image_path}")
        post = self.obsidian_post(file_name)
        cover_path = self.copy_cover_image(image_path, post)
        self.set_post_cover(post, cover_path)
        return post, cover_path

    def obsidian_post(self, file_name: str) -> Path:
        post = self.obsidian_posts_path / file_name
        if not post.exists() or not post.is_file():
            raise FileNotFoundError(f"Obsidian post not found: {post}")
        if post.suffix.lower() != ".md":
            raise ValueError(f"Only Markdown posts are supported: {post}")
        return post

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

    def delete_post(self, file_name: str, keep_obsidian: bool = False) -> tuple[Path | None, Path | None]:
        source = self.obsidian_posts_path / file_name
        trash_target: Path | None = None
        if not keep_obsidian:
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

    def delete_post_and_publish(
        self,
        file_name: str,
        log: LogFn | None = None,
        keep_obsidian: bool = False,
    ) -> tuple[Path | None, Path | None]:
        trash_target, removed_hexo = self.delete_post(file_name, keep_obsidian=keep_obsidian)
        if log:
            if keep_obsidian:
                log(f"已保留 Obsidian 原文：{self.obsidian_posts_path / file_name}")
            elif trash_target:
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
        configured = str(self.config.npm_executable_path).strip()
        if configured:
            candidate = Path(configured)
            if candidate.exists():
                return str(candidate)
            found_configured = shutil.which(configured)
            if found_configured:
                return found_configured

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

    def node_executable(self) -> str:
        found = shutil.which("node.exe") or shutil.which("node")
        if found:
            return found

        try:
            npm_path = Path(self.npm_executable())
        except RuntimeError:
            npm_path = Path()
        if npm_path:
            candidate = npm_path.with_name("node.exe")
            if candidate.exists():
                return str(candidate)

        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "node.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "nodejs" / "node.exe",
            Path("E:/Program Files/nodejs/node.exe"),
            Path("D:/Program Files/nodejs/node.exe"),
            Path("C:/Program Files/nodejs/node.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        raise RuntimeError("找不到 node。请安装 Node.js LTS，或把 node.exe 加入 PATH。")

    def git_executable(self) -> str:
        configured = str(self.config.git_executable).strip() or "git"
        candidate = Path(configured)
        if candidate.exists():
            return str(candidate)
        found = shutil.which(configured)
        if found:
            return found
        raise RuntimeError("找不到 git。请安装 Git，或在设置里选择 git.exe。")

    def resolve_command(self, command: list[str] | str) -> list[str]:
        if isinstance(command, str):
            command = shlex.split(command, posix=False)
        if command and command[0].lower() == "npm":
            return [self.npm_executable(), *command[1:]]
        if command and command[0].lower() == "git":
            return [self.git_executable(), *command[1:]]
        return command


def yaml_scalar(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def discover_repo_root() -> Path:
    starts: list[Path] = [Path.cwd()]
    if getattr(sys, "frozen", False):
        starts.append(Path(sys.executable).resolve().parent)
    starts.append(Path(__file__).resolve().parent)

    for start in starts:
        for path in [start, *start.parents]:
            package_json = path / "package.json"
            if package_json.exists() and (path / ".git").exists():
                return path
            if package_json.exists() and (path / "tools" / "blog").exists():
                return path
    return Path(__file__).resolve().parents[2]


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
