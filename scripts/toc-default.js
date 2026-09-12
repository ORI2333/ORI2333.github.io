/*
 * 默认开启文章目录（TOC）。
 *
 * 主题 sidebar.ejs / post.ejs 渲染 TOC 的条件是 `page.toc`，而本站文章的
 * front-matter 都没有 toc 字段，导致侧栏目录从不显示。这里在模板渲染前把
 * 未显式设置 toc 的文章/页面默认置为 true；front-matter 里写了 `toc: false`
 * 的仍按其意愿关闭。
 */
hexo.extend.filter.register('template_locals', function (locals) {
  const page = locals.page;
  if (page && typeof page.toc === 'undefined') {
    const layout = page.layout;
    if (layout === 'post' || layout === 'page') {
      page.toc = true;
    }
  }
  return locals;
});
