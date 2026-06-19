# 博客工作流工具

在仓库根目录启动图形界面：

```bash
npm run blog
```

也可以直接运行命令行操作：

```bash
npm run blog:sync
npm run blog:preview
npm run blog:publish
npm run blog:check
npm run blog:build-exe
```

封面可以不手填。同步时空封面或占位封面会自动使用默认封面。

图形界面支持：

- `选择封面`：为最近修改的 Obsidian 文章选择本地图片，自动复制到博客图片目录。
- `封面 URL`：为最近修改的 Obsidian 文章写入图床链接。
- 也可以直接在 Obsidian 的 front matter 里写 `https://...`，同步时会原样保留。
- `删除文章`：支持搜索标题/文件名，默认按最近修改排序；确认时显示 Obsidian 原文、回收站目标和 Hexo 文件路径，然后移动原文到 `Blog/Trash`，删除 Hexo 同名文章，并自动构建发布。
- `路径` 区域可以选择 Obsidian 库、`git.exe` 和 `npm.cmd`，换电脑后不需要手改 JSON。
- `环境检查` 会检查 Python/Qt、Git、Node.js、npm、Hexo 依赖、仓库、Obsidian 路径和 Git 状态；缺少环境时会给出下载或处理建议。

发布说明：

- `发布全站` / `一键完成` 会推送 `source` 分支，GitHub Actions 自动部署 GitHub Pages 和香港站点。
- `npm run blog:deploy-hk` 是本机手动兜底命令，仅在 GitHub Actions 或服务器同步排障时使用。

打包说明：

- `npm run blog:build-exe` 会用 PyInstaller 打包 GUI。
- exe 只打包 Python GUI，不内置 Node.js、Git 或博客仓库。
- 新电脑仍需要安装 Git、Node.js，clone 博客仓库，并在 GUI 里选择 Obsidian 库、Git 和 npm 路径。
- 建议把 exe 放在博客仓库内运行，或从仓库根目录启动。打开后先点 `环境检查`。
- 打包结果位于 `dist/blog-gui/YYYYMMDD-HHMMSS/ORI-Blog-Workflow/ORI-Blog-Workflow.exe`，每次使用时间戳目录，避免旧 exe 或 DLL 被占用导致覆盖失败。
