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
npm run blog:deploy-hk
```

封面可以不手填。同步时空封面或占位封面会自动使用默认封面。

图形界面支持：

- `选择封面`：为最近修改的 Obsidian 文章选择本地图片，自动复制到博客图片目录。
- `封面 URL`：为最近修改的 Obsidian 文章写入图床链接。
- 也可以直接在 Obsidian 的 front matter 里写 `https://...`，同步时会原样保留。
- `删除文章`：支持搜索标题/文件名，默认按最近修改排序；确认时显示 Obsidian 原文、回收站目标和 Hexo 文件路径，然后移动原文到 `Blog/Trash`，删除 Hexo 同名文章，并自动构建发布。

发布说明：

- `发布全站` / `一键完成` 会推送 `source` 分支，GitHub Actions 自动部署 GitHub Pages 和香港站点。
- `部署香港` / `npm run blog:deploy-hk` 是本机手动备用部署，正常日常不需要点。
