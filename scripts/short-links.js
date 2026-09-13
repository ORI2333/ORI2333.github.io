/*
 * 为文章生成不含中文的 canonical 短路径。
 *
 * Hexo 内置 post_permalink 过滤器先生成传统日期/标题路径；本过滤器随后
 * 用该路径的 FNV-1a 摘要生成 /s/<id>/。不生成旧路径副本，也不保留中文
 * URL 跳转入口。香港构建的正文位于 /blog/s/<id>/，Pages/EdgeOne 使用
 * /s/<id>/；根域名 /s/<id> 仍由香港网关提供线路选择。
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

hexo.extend.filter.register('post_permalink', function (path) {
  return `/s/${shortId(path)}/`;
}, 11);
