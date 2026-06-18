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
```

封面可以不手填。同步时空封面或占位封面会自动使用默认封面。

图形界面支持：

- `选择封面`：为最近修改的 Obsidian 文章选择本地图片，自动复制到博客图片目录。
- `封面 URL`：为最近修改的 Obsidian 文章写入图床链接。
