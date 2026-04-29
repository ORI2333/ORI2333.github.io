# 博客仓库整改说明

## 整改概述

本仓库已进行重大重构，采用"**源码与静态产物分离**"的标准 GitHub Pages 部署策略，彻底解决了之前的安全隐患和文件冗余问题。

## 主要变更

### 1. 仓库分支结构变更

| 分支 | 用途 | 说明 |
|------|------|------|
| `source` | **源代码仓库**（新默认分支） | 存放所有的源文件：Markdown 文章、配置文件、package.json 等。这是你日常编辑和推送的分支 |
| `main` | **GitHub Pages 产物** | 仅存放编译后的静态 HTML、CSS、JS 文件（`public/` 目录）。GitHub Pages 从该分支读取网站内容 |

### 2. 清理的大型文件和目录

已从 Git 历史中彻底删除：

- ✅ `node_modules/` - Node.js 依赖包（数百 MB）
- ✅ `public/` - 编译产物
- ✅ `.deploy_git/` - Hexo 部署缓存

这些目录现在由 `.gitignore` 保护，不会再被意外提交。

### 3. 部署流程优化

#### 旧流程（存在问题）
```
本地编辑 → git push origin main
↓
main 分支包含：源码 + node_modules + public + 配置文件
↓
问题：安全隐患、冗余、GitHub Pages 可能混淆
```

#### 新流程（推荐）
```
本地编辑 source 分支
↓
git push origin source
↓
GitHub Actions 自动触发
↓
1. npm ci（安装依赖）
2. npm run build（生成 public）
3. 推送 public 到 main 分支
↓
GitHub Pages 从 main 分支读取
↓
网站更新
```

## 日常使用说明

### 基本流程

#### 1. 确保你在 source 分支
```bash
git branch -v
# 应该看到 * source ...
```

#### 2. 编辑文章
在 `source/_posts/` 中创建或修改 Markdown 文件：
```bash
# 创建新文章
npx hexo new post "你的标题"

# 或直接编辑现有文章
```

#### 3. 本地预览
```bash
npm run server
# 访问 http://localhost:4000/blog/
```

#### 4. 提交并推送源码
```bash
git add -A
git commit -m "feat: add new article about xxx"
git push origin source
```

**就这样！** GitHub Actions 会自动构建和部署到 main 分支。

### 脚本命令详解

```bash
# 清空编译产物
npm run clean

# 构建静态网站到 public/
npm run build

# 本地预览服务器
npm run server

# 立即部署 public/ 到远程 main 分支（仅用于本地测试，通常由 CI 处理）
npm run deploy

# 推送源码到 source 分支（自动推送所有更改，触发 GitHub Actions）
npm run push

# 完整部署流程（仅在本地需要立即测试时使用）
npm run push:static
```

## 安全性说明

### ✅ 已解决的安全隐患

1. **敏感配置不再暴露**
   - `_config.yml` 和 `_config.kratos-rebirth.yml` 仅存于 source 分支
   - main 分支只有编译后的静态文件，不包含任何配置代码

2. **依赖包不再上传**
   - `node_modules/` 从未来都不会被追踪
   - GitHub 仓库大小大幅减少
   - 克隆和同步速度显著提升

3. **部署密钥安全**
   - 如使用 SSH 部署密钥，仅需在 GitHub Actions secrets 中配置一次
   - 本地无需保存部署凭证

### ⚠️ 仍需注意

如果你在配置中包含了**第三方服务 API 密钥**（如 Waline AppID、Algolia API Key 等）：

**方案 1：推荐 - 使用 GitHub Secrets**
```yaml
# 在 _config.kratos-rebirth.yml 中使用环境变量
# 例如：waline: ${{ secrets.WALINE_SERVER_URL }}

# 在 GitHub Actions workflow 中设置这些 secrets
env:
  WALINE_SERVER_URL: ${{ secrets.WALINE_SERVER_URL }}
  ALGOLIA_API_KEY: ${{ secrets.ALGOLIA_API_KEY }}
```

**方案 2：分离敏感配置**
创建一个不被追踪的 `.env` 文件或 `_config.local.yml`，在构建时动态合并。

## 常见问题

### Q: 为什么我 push 到 source 后网站没有立即更新？

A: GitHub Actions 需要几秒到几分钟时间来执行构建和部署。你可以：
1. 查看仓库的 **Actions** 标签页，观察工作流执行状态
2. 等待工作流完成后，检查 main 分支是否已更新
3. 清浏览器缓存后刷新网站

### Q: 我能在本地测试部署吗？

A: 可以。执行 `npm run push:static`，它会在本地执行完整流程（构建 → 部署）。但这需要 SSH 访问权限配置好。

### Q: 旧的 main 分支历史丢失了吗？

A: 没有。旧历史仍在，但大部分是删除 node_modules 的记录。你可以随时查看旧提交：
```bash
git log origin/main --oneline | head -20
```

### Q: 如何切换到 main 分支查看部署的产物？

A: 
```bash
git fetch origin
git checkout main
# 或直接查看
git log origin/main --oneline
```

## 下一步建议

1. **验证 GitHub Actions 配置**
   - 进入仓库的 **Settings** > **Actions** > **General**
   - 确保 Actions 已启用

2. **保护分支规则**（可选但推荐）
   ```
   Settings > Branches > Add rule
   - Branch name pattern: main
   - ✅ Require pull request reviews
   - ✅ Require status checks to pass
   ```
   这样可以确保只有通过 CI 检查的代码才能合并到 main。

3. **设置默认分支**
   ```
   Settings > Branches > Default branch
   切换到 source
   ```
   这样新克隆时会默认切到 source 分支。

4. **备份配置**
   建议备份 `_config.yml` 和 `_config.kratos-rebirth.yml`，以防万一。

## 参考链接

- [Hexo 官方部署文档](https://hexo.io/docs/one-command-deployment)
- [GitHub Pages 官方文档](https://docs.github.com/en/pages)
- [GitHub Actions 工作流语法](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)

---

**最后更新**：2026 年 4 月 29 日
