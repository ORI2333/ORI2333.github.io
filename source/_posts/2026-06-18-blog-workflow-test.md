---
title: 博客工作流测试
date: 2026-06-18 01:20:00
tags:
  - 博客网站
  - 工作流
categories:
  - docs
cover: /images/posts/test.webp
draft: false
---

这是一篇用于验证 Obsidian 到 Hexo 同步、构建和发布流程的测试文章。

<!-- more -->

如果你能在博客里看到这篇文章，说明新的 Python + Qt 图形化博客工作流已经可以正常完成日常发布链路。

## 测试项

- Obsidian `Blog/Posts` 文章同步到 Hexo `source/_posts`
- `draft: false` 的文章允许发布
- Hexo 本地构建通过
- 后续可通过 `npm run blog` 打开图形界面继续维护
