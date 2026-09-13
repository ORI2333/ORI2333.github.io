/*
 * 把 tools/vendor/mermaid.min.js 以路由形式发布到 js/vendor/mermaid.min.js。
 *
 * 不能把它放进 source/ 让 Hexo asset 处理器搬运：mermaid 压缩产物内部
 * 存在长横线序列，hexo-front-matter 的 rFrontMatterNew 会把文件前半段
 * 误判为 YAML front-matter 并抛异常，导致该文件被静默跳过、不进路由。
 * generator 方式绕开 asset 流水线，且 hexo server 预览同样可用；
 * 输出位置跟随 public_dir（HK 构建 public/blog 也正确）。
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(hexo.base_dir, 'tools', 'vendor', 'mermaid.min.js');

hexo.extend.generator.register('mermaid-vendor', function () {
  if (!fs.existsSync(SRC)) {
    hexo.log.warn('mermaid.min.js missing:', SRC);
    return [];
  }
  return {
    path: 'js/vendor/mermaid.min.js',
    data: () => fs.createReadStream(SRC),
  };
});
