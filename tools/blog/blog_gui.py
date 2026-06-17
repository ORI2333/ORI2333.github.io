from __future__ import annotations

import sys

try:
    from PySide6.QtCore import QObject, QProcess, QThread, Signal as pyqtSignal
    from PySide6.QtWidgets import (
        QApplication,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
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
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QLineEdit,
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
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

from blog_core import BlogWorkflow, open_path


class Worker(QObject):
    log = pyqtSignal(str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, action: str, title: str | None = None):
        super().__init__()
        self.action = action
        self.title = title

    def run(self) -> None:
        workflow = BlogWorkflow()
        try:
            if self.action == "status":
                self.done.emit("\n".join(workflow.status_lines()))
            elif self.action == "new":
                assert self.title is not None
                path = workflow.create_post(self.title, open_after=True)
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
                workflow.publish(self.log.emit)
                self.done.emit("发布完成。")
            elif self.action == "all":
                posts, drafts, assets = workflow.all(self.log.emit)
                self.done.emit(f"全部完成：同步 {posts} 篇文章，跳过 {drafts} 篇草稿，复制 {assets} 个资源。")
            elif self.action == "open-vault":
                open_path(workflow.require_vault())
                self.done.emit("已打开 Obsidian vault。")
        except Exception as exc:
            self.failed.emit(str(exc))


class BlogWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.workflow = BlogWorkflow()
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.process: QProcess | None = None

        self.setWindowTitle("博客工作流")
        self.resize(920, 620)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self.make_paths_box())
        layout.addWidget(self.make_actions_box())

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        no_wrap = getattr(QTextEdit, "NoWrap", QTextEdit.LineWrapMode.NoWrap)
        self.log.setLineWrapMode(no_wrap)
        layout.addWidget(self.log, 1)

        self.setCentralWidget(root)
        self.write_log("就绪。")
        self.write_log("\n".join(self.workflow.status_lines()))

    def make_paths_box(self) -> QGroupBox:
        box = QGroupBox("路径")
        layout = QGridLayout(box)
        self.repo_field = QLineEdit(str(self.workflow.repo_root))
        self.vault_field = QLineEdit(str(self.workflow.config.obsidian_vault_path))
        for field in (self.repo_field, self.vault_field):
            field.setReadOnly(True)
        layout.addWidget(QLabel("博客仓库"), 0, 0)
        layout.addWidget(self.repo_field, 0, 1)
        layout.addWidget(QLabel("Obsidian 库"), 1, 0)
        layout.addWidget(self.vault_field, 1, 1)
        return box

    def make_actions_box(self) -> QGroupBox:
        box = QGroupBox("操作")
        layout = QHBoxLayout(box)
        actions = [
            ("新建草稿", self.new_post),
            ("导入到 Obsidian", lambda: self.run_worker("import")),
            ("同步到 Hexo", lambda: self.run_worker("sync")),
            ("构建检查", lambda: self.run_worker("build")),
            ("本地预览", self.preview),
            ("发布", lambda: self.run_worker("publish")),
            ("一键完成", lambda: self.run_worker("all")),
            ("打开 Obsidian", lambda: self.run_worker("open-vault")),
            ("查看状态", lambda: self.run_worker("status")),
        ]
        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        return box

    def new_post(self) -> None:
        title, ok = QInputDialog.getText(self, "新建草稿", "文章标题：")
        if ok and title.strip():
            self.run_worker("new", title.strip())

    def run_worker(self, action: str, title: str | None = None) -> None:
        if self.thread is not None:
            QMessageBox.information(self, "正在处理", "已有任务正在运行。")
            return
        self.write_log(f"\n> {action}")
        self.thread = QThread()
        self.worker = Worker(action, title)
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


if __name__ == "__main__":
    raise SystemExit(main())
