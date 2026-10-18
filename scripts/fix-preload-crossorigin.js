// 主题给 CSS 生成了 <link rel="preload" ... crossorigin>，但对应的
// <link rel="stylesheet"> 没有 crossorigin。同源资源带与不带 crossorigin 的请求
// 凭证模式不同，浏览器不认为是同一个请求，于是 preload 白下、CSS 又下载一遍
// （控制台会提示 "A preload for ... is found, but is not used because the request
// credentials mode does not match"）。本站 CSS 都是同源路径，去掉这个属性即可命中 preload。
// 只处理同源（href 不是 http/https 开头）的 preload，避免以后换成 CDN 时误伤。
hexo.extend.filter.register('after_render:html', (html) =>
  html.replace(/<link rel="preload"[^>]*>/g, (tag) =>
    /href="(?!https?:)/.test(tag) ? tag.replace(/\s*crossorigin(?=[\s>])/, '') : tag,
  ),
);
