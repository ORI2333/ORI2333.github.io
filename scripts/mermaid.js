/*
 * Mermaid 图表渲染支持。
 *
 * 关键点：Hexo 核心的 before_post_render 过滤器 backtick_code_block（优先级 10）
 * 会在 marked 渲染之前，把所有 ```围栏代码块转成 <figure class="highlight">。
 * 因此必须在它之前拦截：这里注册优先级 9 的 before_post_render 过滤器，把
 * ```mermaid 块直接替换为 <div class="mermaid" data-code="...">，绕开高亮处理。
 * 由 after_footer 注入的脚本按需加载 mermaid.min.js（自托管 source/js/vendor/）
 * 并在浏览器端渲染；data-code 存 URI 编码原文，供主题切换时重绘。
 */
const MERMAID_FENCE = /(^|\n)[ \t]*(?:```|~~~)[ \t]*mermaid[ \t]*\n([\s\S]*?)\n[ \t]*(?:```|~~~)[ \t]*(?=\n|$)/g;

function escapeHtml(text) {
  // &#123;/&#125; 转义花括号：mermaid 的 {{六边形}} 语法会被 nunjucks 当模板吞掉
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/{/g, '&#123;')
    .replace(/}/g, '&#125;');
}

hexo.extend.filter.register('before_post_render', function (data) {
  if (!data.content || data.content.indexOf('mermaid') === -1) return data;
  data.content = data.content.replace(MERMAID_FENCE, function (_m, lead, code) {
    const encoded = encodeURIComponent(code.replace(/\n$/, ''));
    return `${lead}<div class="mermaid" data-code="${encoded}">${escapeHtml(code)}</div>`;
  });
  return data;
}, 9);
