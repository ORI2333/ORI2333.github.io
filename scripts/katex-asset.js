/*
 * 将 KaTeX 浏览器资源以 Hexo 路由形式发布。
 *
 * 不经 source/ asset 流水线，避免压缩 JavaScript 被 hexo-front-matter 误判。
 * CSS 位于 css/vendor/，与其相对引用的 fonts/ 同目录发布；只保留现代浏览器
 * 实际使用的 WOFF2 字体，页面按需加载相应字形。
 */
const fs = require('fs');
const path = require('path');

const DIST = path.join(hexo.base_dir, 'node_modules', 'katex', 'dist');
const FONTS = path.join(DIST, 'fonts');
const FILES = [
  ['css/vendor/katex.min.css', path.join(DIST, 'katex.min.css')],
  ['js/vendor/katex.min.js', path.join(DIST, 'katex.min.js')],
];

function stream(file) {
  return function () {
    return fs.createReadStream(file);
  };
}

hexo.extend.generator.register('katex-vendor', function () {
  if (!fs.existsSync(DIST) || !fs.existsSync(FONTS)) {
    hexo.log.warn('KaTeX distribution missing:', DIST);
    return [];
  }

  const routes = FILES.map(function ([route, file]) {
    return {path: route, data: stream(file)};
  });
  for (const file of fs.readdirSync(FONTS)) {
    if (file.endsWith('.woff2')) {
      routes.push({
        path: `css/vendor/fonts/${file}`,
        data: stream(path.join(FONTS, file)),
      });
    }
  }
  return routes;
});
