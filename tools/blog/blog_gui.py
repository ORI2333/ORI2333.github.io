from __future__ import annotations

import sys
from pathlib import Path

try:
    from PySide6.QtCore import QObject, QProcess, QThread, Signal as pyqtSignal
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:
    try:
        from PyQt6.QtCore import QObject, QProcess, QThread, pyqtSignal
        from PyQt6.QtWidgets import (
            QApplication,
            QDialog,
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QLineEdit,
            QListWidget,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ModuleNotFoundError:
        from PyQt5.QtCore import QObject, QProcess, QThread, pyqtSignal
        from PyQt5.QtWidgets import (
            QApplication,
            QDialog,
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QLineEdit,
            QListWidget,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

from blog_core import BlogWorkflow, open_path


STYLE = """
QMainWindow {
    background: #f3f6f8;
}
QWidget {
    color: #17212f;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame#Hero {
    background: #15202b;
    border-radius: 8px;
}
QFrame#Card {
    background: #ffffff;
    border: 1px solid #d8e0ea;
    border-radius: 8px;
}
QLabel#HeroTitle {
    color: #ffffff;
    font-size: 22px;
    font-weight: 700;
}
QLabel#HeroSub {
    color: #c8d4df;
    font-size: 13px;
}
QLabel#SectionTitle {
    color: #17212f;
    font-size: 15px;
    font-weight: 700;
}
QLabel#Muted {
    color: #647386;
}
QLineEdit {
    min-height: 30px;
    padding: 4px 9px;
    border: 1px solid #d4dde8;
    border-radius: 6px;
    background: #f8fafc;
}
QPushButton {
    min-height: 32px;
    padding: 5px 12px;
    border-radius: 6px;
    border: 1px solid #c9d4df;
    background: #ffffff;
    color: #17212f;
}
QPushButton:hover {
    background: #eef6f5;
    border-color: #8fbdb8;
}
QPushButton[variant="primary"] {
    background: #176b66;
    color: white;
    border-color: #176b66;
    font-weight: 700;
}
QPushButton[variant="primary"]:hover {
    background: #125753;
}
QPushButton[variant="danger"] {
    background: #fff5ec;
    color: #95430d;
    border-color: #f5c99d;
}
QTextEdit {
    background: #101820;
    color: #d5e3df;
    border: 1px solid #22303a;
    border-radius: 8px;
    padding: 10px;
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 12px;
}
QListWidget {
    border: 1px solid #d6dfec;
    border-radius: 6px;
    background: #ffffff;
    padding: 4px;
}
QListWidget::item {
    min-height: 28px;
    padding: 4px 6px;
}
QListWidget::item:selected {
    background: #d9eeea;
    color: #17212f;
}
"""


class Worker(QObject):
    log = pyqtSignal(str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, action: str, value: str | None = None):
        super().__init__()
        self.action = action
        self.value = value

    def run(self) -> None:
        workflow = BlogWorkflow()
        try:
            if self.action == "status":
                self.done.emit("\n".join(workflow.status_lines()))
            elif self.action == "new":
                assert self.value is not None
                path = workflow.create_post(self.value, open_after=True)
                self.done.emit(f"已创建草稿：{path}")
            elif self.action == "import":
                posts, assets = workflow.import_to_obsidian(self.log.emit)
                self.done.emit(f"已导入 {posts} 篇文章和 {assets} 个资源。")
            elif self.action == "sync":
                posts, drafts, assets = workflow.sync_to_hexo(self.log.emit)
                self.done.emit(f"已同步 {posts} 篇文章，跳过 {drafts} 篇草稿，复制 {assets} 个资源。")
            elif self.action == "build":
                workflow.build(self.log.emit)
                self.done.emit("构建完成。")
            elif self.action == "publish":
                workflow.publish_all_targets(self.log.emit)
                self.done.emit("发布完成。")
            elif self.action == "deploy-hk":
                workflow.deploy_hk(self.log.emit)
                self.done.emit("香港站点部署完成。")
            elif self.action == "all":
                posts, drafts, assets = workflow.all(self.log.emit)
                self.done.emit(f"全部完成：同步 {posts} 篇文章，跳过 {drafts} 篇草稿，复制 {assets} 个资源。")
            elif self.action == "open-vault":
                open_path(workflow.require_vault())
                self.done.emit("已打开 Obsidian 库。")
            elif self.action == "cover-url":
                assert self.value is not None
                path = workflow.set_latest_cover_url(self.value)
                self.done.emit(f"已设置最近文章封面链接：{path}")
            elif self.action == "cover-file":
                assert self.value is not None
                path, cover = workflow.set_latest_cover_file(self.value)
                self.done.emit(f"已设置最近文章封面：{path}\n封面路径：{cover}")
            elif self.action == "delete-post":
                assert self.value is not None
                trash, removed = workflow.delete_post_and_publish(self.value, self.log.emit)
                if removed:
                    self.done.emit(f"删除并发布完成。\n已移动到回收站：{trash}\n已从 Hexo 删除：{removed}")
                else:
                    self.done.emit(f"删除并发布完成。\n已移动到回收站：{trash}\nHexo 中没有同名文章。")
            elif self.action == "check-env":
                self.done.emit("\n".join(workflow.environment_report()))
        except Exception as exc:
            self.failed.emit(str(exc))


class DeletePostDialog(QDialog):
    def __init__(self, posts: list[Path], parent=None):
        super().__init__(parent)
        self.posts = sorted(posts, key=lambda path: path.stat().st_mtime, reverse=True)
        self.filtered_posts = list(self.posts)
        self.selected_name: str | None = None

        self.setWindowTitle("删除文章")
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("选择要删除的文章")
        title.setObjectName("SectionTitle")
        hint = QLabel("默认按最近修改排序。可以搜索标题或文件名。")
        hint.setObjectName("Muted")

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题或文件名")
        self.search.textChanged.connect(self.refresh_list)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self.accept_selected())

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        delete = QPushButton("继续删除")
        delete.setProperty("variant", "danger")
        cancel.clicked.connect(self.reject)
        delete.clicked.connect(self.accept_selected)
        buttons.addWidget(cancel)
        buttons.addWidget(delete)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.search)
        layout.addWidget(self.list_widget, 1)
        layout.addLayout(buttons)
        self.refresh_list()

    def refresh_list(self) -> None:
        keyword = self.search.text().strip().lower()
        self.list_widget.clear()
        self.filtered_posts = []
        for post in self.posts:
            haystack = f"{post.name} {read_post_title(post)}".lower()
            if keyword and keyword not in haystack:
                continue
            self.filtered_posts.append(post)
            self.list_widget.addItem(f"{read_post_title(post)}    ({post.name})")
        if self.filtered_posts:
            self.list_widget.setCurrentRow(0)

    def accept_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.filtered_posts):
            QMessageBox.information(self, "删除文章", "请先选择一篇文章。")
            return
        self.selected_name = self.filtered_posts[row].name
        self.accept()


class BlogWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.workflow = BlogWorkflow()
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.process: QProcess | None = None

        self.setWindowTitle("ORI 博客工作台")
        self.resize(1080, 720)
        self.setStyleSheet(STYLE)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        outer.addWidget(self.make_hero())
        outer.addWidget(self.make_paths_card())
        outer.addWidget(self.make_actions_card())
        outer.addWidget(self.make_log_card(), 1)

        self.setCentralWidget(root)
        self.write_log("就绪。建议先点“环境检查”，确认 Git、Node、Obsidian 和仓库状态。")

    def make_hero(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Hero")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel("ORI 博客工作台")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("Obsidian 写作，Hexo 构建，GitHub Actions 自动发布到多线路站点")
        subtitle.setObjectName("HeroSub")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def make_paths_card(self) -> QFrame:
        frame = self.card()
        layout = QGridLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        title = QLabel("路径")
        title.setObjectName("SectionTitle")
        layout.addWidget(title, 0, 0, 1, 2)

        self.repo_field = self.readonly_field(str(self.workflow.repo_root))
        self.vault_field = self.readonly_field(str(self.workflow.config.obsidian_vault_path))
        self.git_field = self.readonly_field(self.workflow.config.git_executable)
        self.npm_field = self.readonly_field(self.workflow.config.npm_executable_path or "自动检测")
        self.cover_field = self.readonly_field(self.workflow.config.default_cover)

        layout.addWidget(self.muted("博客仓库"), 1, 0)
        layout.addWidget(self.repo_field, 1, 1)
        layout.addWidget(self.muted("Obsidian 库"), 2, 0)
        vault_row = QHBoxLayout()
        vault_row.addWidget(self.vault_field, 1)
        vault_row.addWidget(self.button("选择", self.choose_vault))
        layout.addLayout(vault_row, 2, 1)
        layout.addWidget(self.muted("Git"), 3, 0)
        git_row = QHBoxLayout()
        git_row.addWidget(self.git_field, 1)
        git_row.addWidget(self.button("选择", self.choose_git))
        layout.addLayout(git_row, 3, 1)
        layout.addWidget(self.muted("npm"), 4, 0)
        npm_row = QHBoxLayout()
        npm_row.addWidget(self.npm_field, 1)
        npm_row.addWidget(self.button("选择", self.choose_npm))
        layout.addLayout(npm_row, 4, 1)
        layout.addWidget(self.muted("默认封面"), 5, 0)
        layout.addWidget(self.cover_field, 5, 1)
        return frame

    def make_actions_card(self) -> QFrame:
        frame = self.card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title = QLabel("操作")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self.button("新建草稿", self.new_post, "primary"))
        row1.addWidget(self.button("同步到 Hexo", lambda: self.run_worker("sync"), "primary"))
        row1.addWidget(self.button("构建检查", lambda: self.run_worker("build")))
        row1.addWidget(self.button("本地预览", self.preview))
        row1.addWidget(self.button("发布全站", lambda: self.run_worker("publish"), "danger"))
        row1.addWidget(self.button("一键完成", lambda: self.run_worker("all"), "danger"))
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self.button("选择封面", self.pick_cover_file))
        row2.addWidget(self.button("封面 URL", self.set_cover_url))
        row2.addWidget(self.button("删除文章", self.delete_post, "danger"))
        row2.addWidget(self.button("导入到 Obsidian", lambda: self.run_worker("import")))
        row2.addWidget(self.button("打开 Obsidian", lambda: self.run_worker("open-vault")))
        row2.addWidget(self.button("环境检查", lambda: self.run_worker("check-env")))
        row2.addWidget(self.button("查看状态", lambda: self.run_worker("status")))
        row2.addStretch(1)
        layout.addLayout(row2)
        return frame

    def make_log_card(self) -> QFrame:
        frame = self.card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 14)
        title = QLabel("日志")
        title.setObjectName("SectionTitle")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        no_wrap = getattr(QTextEdit, "NoWrap", QTextEdit.LineWrapMode.NoWrap)
        self.log.setLineWrapMode(no_wrap)
        layout.addWidget(title)
        layout.addWidget(self.log, 1)
        return frame

    def card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        return frame

    def muted(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        return label

    def readonly_field(self, value: str) -> QLineEdit:
        field = QLineEdit(value)
        field.setReadOnly(True)
        return field

    def button(self, text: str, callback, variant: str | None = None) -> QPushButton:
        btn = QPushButton(text)
        if variant:
            btn.setProperty("variant", variant)
        btn.clicked.connect(callback)
        return btn

    def new_post(self) -> None:
        title, ok = QInputDialog.getText(self, "新建草稿", "文章标题：")
        if ok and title.strip():
            self.run_worker("new", title.strip())

    def pick_cover_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择最近文章封面",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.gif);;所有文件 (*.*)",
        )
        if path:
            self.run_worker("cover-file", path)

    def set_cover_url(self) -> None:
        url, ok = QInputDialog.getText(self, "设置最近文章封面 URL", "图片链接：")
        if ok and url.strip():
            self.run_worker("cover-url", url.strip())

    def choose_vault(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择 Obsidian 库",
            str(self.workflow.config.obsidian_vault_path) if str(self.workflow.config.obsidian_vault_path) else "",
        )
        if not path:
            return
        self.workflow.update_config(obsidianVaultPath=path.replace("\\", "/"))
        self.refresh_config_fields()
        self.write_log(f"已更新 Obsidian 库：{path}")

    def choose_git(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 git.exe",
            "",
            "Git 可执行文件 (git.exe);;所有文件 (*.*)",
        )
        if not path:
            return
        self.workflow.update_config(gitExecutable=path.replace("\\", "/"))
        self.refresh_config_fields()
        self.write_log(f"已更新 Git：{path}")

    def choose_npm(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 npm.cmd",
            "",
            "npm 可执行文件 (npm.cmd npm);;所有文件 (*.*)",
        )
        if not path:
            return
        self.workflow.update_config(npmExecutable=path.replace("\\", "/"))
        self.refresh_config_fields()
        self.write_log(f"已更新 npm：{path}")

    def refresh_config_fields(self) -> None:
        self.vault_field.setText(str(self.workflow.config.obsidian_vault_path))
        self.git_field.setText(self.workflow.config.git_executable)
        self.npm_field.setText(self.workflow.config.npm_executable_path or "自动检测")
        self.cover_field.setText(self.workflow.config.default_cover)

    def delete_post(self) -> None:
        posts = self.workflow.list_obsidian_posts()
        if not posts:
            QMessageBox.information(self, "删除文章", "Obsidian 文章目录里没有 Markdown 文件。")
            return
        dialog = DeletePostDialog(posts, self)
        if run_dialog(dialog) != accepted_dialog_code():
            return
        name = dialog.selected_name
        if not name:
            return
        source = self.workflow.obsidian_posts_path / name
        trash = self.workflow.unique_trash_path(name)
        hexo = self.workflow.hexo_posts_path / name
        reply = QMessageBox.question(
            self,
            "确认删除并发布",
            "请确认这次删除操作：\n\n"
            f"文章：{name}\n\n"
            f"Obsidian 原文：\n{source}\n\n"
            f"移动到回收站：\n{trash}\n\n"
            f"删除 Hexo 文件：\n{hexo}\n\n"
            "随后会自动构建并发布，让线上页面同步下线。",
        )
        yes = QMessageBox.StandardButton.Yes if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes
        if reply == yes:
            self.run_worker("delete-post", name)

    def run_worker(self, action: str, value: str | None = None) -> None:
        if self.thread is not None:
            QMessageBox.information(self, "正在处理", "已有任务正在运行。")
            return
        self.write_log(f"\n> {action}")
        self.thread = QThread()
        self.worker = Worker(action, value)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.write_log)
        self.worker.done.connect(self.task_done)
        self.worker.failed.connect(self.task_failed)
        self.worker.done.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_thread)
        self.thread.start()

    def preview(self) -> None:
        if self.process is not None:
            QMessageBox.information(self, "本地预览", "预览服务已经在运行。")
            return
        port = str(self.workflow.config.preferred_preview_port)
        self.write_log(f"\n> npm run server -- -p {port}")
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.workflow.repo_root))
        self.process.setProgram(self.workflow.npm_executable())
        self.process.setArguments(["run", "server", "--", "-p", port])
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.readyReadStandardError.connect(self.read_process_output)
        self.process.finished.connect(self.preview_finished)
        self.process.start()

    def read_process_output(self) -> None:
        assert self.process is not None
        data = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        err = bytes(self.process.readAllStandardError()).decode(errors="replace")
        for text in (data, err):
            if text:
                self.write_log(text.rstrip())

    def preview_finished(self) -> None:
        self.write_log("预览服务已停止。")
        self.process = None

    def task_done(self, message: str) -> None:
        self.write_log(message)

    def task_failed(self, message: str) -> None:
        self.write_log(f"错误：{message}")
        QMessageBox.critical(self, "博客工作流", message)

    def clear_thread(self) -> None:
        self.worker = None
        self.thread = None

    def write_log(self, message: str) -> None:
        self.log.append(message)

    def closeEvent(self, event) -> None:
        if self.process is not None:
            self.process.kill()
            self.process = None
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = BlogWindow()
    window.show()
    if hasattr(app, "exec"):
        return app.exec()
    return app.exec_()


def run_dialog(dialog: QDialog):
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def accepted_dialog_code():
    if hasattr(QDialog, "DialogCode"):
        return QDialog.DialogCode.Accepted
    return QDialog.Accepted


def read_post_title(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError:
        return path.stem
    match = re_search_title(content)
    return match or path.stem


def re_search_title(content: str) -> str | None:
    import re

    match = re.search(r"(?im)^title\s*:\s*(.*?)\s*$", content)
    if not match:
        return None
    return match.group(1).strip().strip("'\"") or None


if __name__ == "__main__":
    raise SystemExit(main())
