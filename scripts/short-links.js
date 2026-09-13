/*
 * 为 GitHub Pages 等根站点生成域名本地短链入口。
 *
 * 香港站点的 /s/<id> 由根目录 gateway 解析并提供线路选择，因此 HK 构建
 * （root 为 /blog/）跳过这里；Pages 构建则生成 /s/<id>/index.html，直接
 * 跳转到同一域名下的文章。短 ID 与 HK 的 share-map.json 使用同一 FNV-1a
 * 算法，保证不同域名上的同一文章拥有相同 ID。
 */

function normalizedPath(value) {
  let path = '/' + String(value || '').replace(/^\/+/, '');
  path = path.replace(/\/index\.html\/?$/i, '/');
  path = path.replace(/\/{2,}/g, '/');
  return path.endsWith('/') ? path : `${path}/`;
}

function shortId(path) {
  const bytes = Buffer.from(normalizedPath(path), 'utf8');
  let hash = 2166136261;
  for (const byte of bytes) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash.toString(36).padStart(7, '0');
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function redirectHtml(targetPath) {
  const target = normalizedPath(targetPath);
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="robots" content="noindex">
  <link rel="canonical" href="${escapeHtml(target)}">
  <meta http-equiv="refresh" content="0;url=${escapeHtml(target)}">
  <title>正在打开文章…</title>
</head>
<body>
  <p>正在打开文章。如果没有自动跳转，请<a href="${escapeHtml(target)}">点击这里</a>。</p>
  <script>location.replace(${JSON.stringify(target)} + location.search + location.hash);</script>
</body>
</html>
`;
}

hexo.extend.generator.register('local-short-links', function () {
  const root = normalizedPath(hexo.config.root || '/');
  if (root !== '/') return [];

  const posts = hexo.locals.get('posts');
  const routes = [];
  posts.forEach(function (post) {
    const articlePath = normalizedPath(post.path || '');
    if (articlePath === '/') return;
    routes.push({
      path: `s/${shortId(articlePath)}/index.html`,
      data: redirectHtml(articlePath),
    });
  });
  return routes;
});
