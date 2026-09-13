/*
 * KaTeX 数学公式预处理。
 *
 * Hexo 的 Markdown 渲染器会把 TeX 中的下划线、星号等符号当作 Markdown
 * 语法处理。这里在 Markdown 渲染前将公式替换为带 URI 编码原文的 HTML 占位符，
 * 保留代码块与行内代码不变；浏览器端加载的 KaTeX 再把占位符渲染为数学公式。
 *
 * 支持 $...$、$$...$$、\(...\) 与 \[...\] 四种常见分隔符。
 */
const FENCED_BLOCK = /^[ \t]*(`{3,}|~{3,})[^\n]*\n[\s\S]*?^[ \t]*\1[ \t]*(?=\n|$)/gm;
const INLINE_CODE = /(`+)([\s\S]*?)\1/g;
const DISPLAY_DOLLAR = /(^|\n)[ \t]*\$\$[ \t]*(?:\n|$)([\s\S]*?)(?:\n|^)[ \t]*\$\$[ \t]*(?=\n|$)/gm;
const DISPLAY_BRACKET = /(^|[^\\])\\\[([\s\S]*?)\\\]/g;
const INLINE_DOLLAR = /(^|[^\\$])\$([^\s$](?:[^$\n]*?[^\s$])?)\$(?!\$)/g;
const INLINE_PAREN = /(^|[^\\])\\\(([^\n]*?)\\\)/g;

function escapeHtml(text) {
  // 花括号也要转义，避免 Nunjucks 将 TeX 的 {{...}} 视为模板表达式。
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/_/g, '&#95;')
    .replace(/{/g, '&#123;')
    .replace(/}/g, '&#125;');
}

function placeholder(tex, display) {
  const source = tex.trim();
  if (!source) return display ? '$$\n$$' : '$$';
  const tag = display ? 'div' : 'span';
  const classes = display ? 'math math-display' : 'math math-inline';
  return `<${tag} class="${classes}" data-tex="${encodeURIComponent(source)}">${escapeHtml(source)}</${tag}>`;
}

function protectInlineCode(text) {
  const saved = [];
  const content = text.replace(INLINE_CODE, function (match) {
    const key = `\u0000ORI_MATH_CODE_${saved.length}\u0000`;
    saved.push(match);
    return key;
  });
  return {
    content,
    restore: function (value) {
      return value.replace(/\u0000ORI_MATH_CODE_(\d+)\u0000/g, function (_match, index) {
        return saved[Number(index)];
      });
    },
  };
}

function transformText(text) {
  const protectedCode = protectInlineCode(text);
  let value = protectedCode.content;

  value = value.replace(DISPLAY_DOLLAR, function (_match, lead, tex) {
    return `${lead}${placeholder(tex, true)}`;
  });
  value = value.replace(DISPLAY_BRACKET, function (_match, lead, tex) {
    return `${lead}${placeholder(tex, true)}`;
  });
  value = value.replace(INLINE_DOLLAR, function (_match, lead, tex) {
    return `${lead}${placeholder(tex, false)}`;
  });
  value = value.replace(INLINE_PAREN, function (_match, lead, tex) {
    return `${lead}${placeholder(tex, false)}`;
  });

  return protectedCode.restore(value);
}

function transformContent(content) {
  let result = '';
  let offset = 0;
  let match;
  FENCED_BLOCK.lastIndex = 0;
  while ((match = FENCED_BLOCK.exec(content)) !== null) {
    result += transformText(content.slice(offset, match.index));
    result += match[0];
    offset = match.index + match[0].length;
  }
  return result + transformText(content.slice(offset));
}

hexo.extend.filter.register('before_post_render', function (data) {
  if (!data.content || !/[\\$]/.test(data.content)) return data;
  data.content = transformContent(data.content);
  return data;
}, 8);
