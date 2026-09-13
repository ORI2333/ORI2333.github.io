/*
 * 为文章生成不含中文的 canonical 短路径，并为旧长路径保留跳转。
 *
 * 短 ID 取自原有日期/标题 permalink 的 FNV-1a 摘要，因此已有 share-map
 * 和历史短链继续有效。文章正文在 /s/<id>/ 输出；旧的中文路径只负责
 * 语义等价的跳转。香港构建仍保留根目录 gateway，文章正文位于
 * /blog/s/<id>/；GitHub Pages 和 EdgeOne 使用 /s/<id>/。
 */
const defaultPostPermalink = require('hexo/dist/plugins/filter/post_permalink');

function normalizedPath(value) {
  let path = '/' + String(value || '').replace(/^\/+/, '');
  path = path.replace(/\/index\.html\/?$/i, '/');
  path = path.replace(/\/{2,}/g, '/');
  return path.endsWith('/') ? path : `${path}/`;
}

function legacyPath(post) {
  return normalizedPath(defaultPostPermalink.call(hexo, post));
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

function shortPathFromLegacy(path) {
  return `/s/${shortId(path)}/`;
}

function deployedPath(path) {
  return normalizedPath(`${hexo.config.root || '/'}${path}`);
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

// Hexo 内置过滤器先生成传统路径；本过滤器再把它替换为短路径。
hexo.extend.filter.register('post_permalink', function (path) {
  return shortPathFromLegacy(path);
}, 11);

// 旧日期/中文路径保留入口，避免历史链接失效。
hexo.extend.generator.register('legacy-post-redirects', function () {
  const posts = hexo.locals.get('posts');
  const routes = [];
  posts.forEach(function (post) {
    const oldPath = legacyPath(post);
    const newPath = normalizedPath(post.path || '');
    if (oldPath === newPath) return;
    routes.push({
      path: `${oldPath.slice(1)}index.html`,
      data: redirectHtml(deployedPath(newPath)),
    });
  });
  return routes;
});
