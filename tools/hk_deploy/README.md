# 香港服务器静态托管

目标：把 Hexo 生成的 `public/` 同步到香港服务器的独立目录，不碰已有服务。

默认配置：

- 服务器：`45.192.104.98`
- SSH 端口：`22`
- 远程目录：`/var/www/ori2333-blog`
- 域名：`blog.orizhen.xyz`、`www.blog.orizhen.xyz`
- 访问方式：真实域名，不使用临时端口

首次使用：

1. 把域名解析到 `45.192.104.98`。
2. 修改 `tools/hk_deploy/hk_deploy.config.json`：
   - `nginxServerName`：你的真实域名，例如 `blog.orizhen.xyz www.blog.orizhen.xyz`
   - `publicUrl`：公开访问地址，例如 `https://blog.orizhen.xyz/`
3. 把部署公钥加入服务器的 `/root/.ssh/authorized_keys`：

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMuVx1IefI3+10NadG5NcO0UWtLsgq7qJ/UMLLlId3uE ori2333-blog-hk
```

4. 初始化服务器 Nginx：

```bash
npm run deploy:hk:setup
```

日常部署：

```bash
npm run deploy:hk
```

当前状态：

- `https://blog.orizhen.xyz/` 是站点选择页，支持黑白主题切换。
- `https://blog.orizhen.xyz/blog/` 是香港服务器上的博客本体。
- 旧的 `/hk/` 路径会重定向到 `/blog/`。
- 选择页的三个入口在 `tools/hk_deploy/hk_deploy.config.json` 中维护：`edgeOneUrl`、`hkBlogPath`、`githubPagesUrl`。
- HTTPS 使用 Let's Encrypt。证书有效期 90 天，服务器上需要保持 `certbot.timer` 或等效 cron 续签任务启用。
- 香港部署会使用 `tools/hk_deploy/_config.hk.yml` 覆盖 Hexo 的 `url`，避免页面 canonical 仍指向 GitHub Pages。

脚本只同步到 `/var/www/ori2333-blog`，不会清理其他目录。Nginx 配置使用明确的 `server_name`，避免接管服务器已有默认站点。

不要把 SSH 密码写进配置或脚本。建议使用 SSH key。
