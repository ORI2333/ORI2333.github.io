/*
 * 自定义 404 页：移植参考设计的"暗色大厅 + 大字辉光 + 浮动光点"风格，
 * 配色改用站点主题色（蓝→绿），素材复用现有 bg-dark.webp。
 * 通过覆盖主题视图 _pages/404 实现，保留主题的导航与页脚布局。
 */
const TEMPLATE = `
<style>
.ori-404-hero{position:relative;isolation:isolate;width:100%;flex:1 0 100%;min-height:clamp(440px,62vh,660px);overflow:hidden;border-radius:16px;background:#0b0e15;margin:12px 0 30px;}
.ori-404-bg{position:absolute;inset:0;z-index:-3;width:100%;height:100%;object-fit:cover;object-position:center 42%;filter:brightness(.7) saturate(.95);}
.ori-404-glow{position:absolute;inset:0;z-index:-2;mix-blend-mode:screen;background:radial-gradient(50% 60% at 60% 50%,rgba(81,173,237,.3),transparent 68%),radial-gradient(42% 52% at 22% 80%,rgba(120,206,121,.2),transparent 70%);animation:ori404breathe 14s ease-in-out infinite alternate;}
.ori-404-fade{position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(11,14,21,.62),transparent 40%,transparent 74%,rgba(11,14,21,.88));}
.ori-404-content{position:relative;z-index:2;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:clamp(440px,62vh,660px);text-align:center;padding:40px 20px;color:#f6f8fb;}
.ori-404-eyebrow{font-family:Consolas,monospace;font-size:12px;letter-spacing:.34em;color:#9fd4ef;margin:0 0 6px;text-transform:uppercase;text-shadow:0 2px 12px rgba(0,0,0,.8);}
.ori-404-code{font-family:Georgia,'Times New Roman',serif;font-size:clamp(120px,17vw,230px);font-weight:700;line-height:.84;color:transparent;background:linear-gradient(166deg,#fff 6%,#dff0fb 42%,#9fd4ef 74%,#6fb7d8 100%);-webkit-background-clip:text;background-clip:text;filter:drop-shadow(0 16px 32px rgba(0,0,0,.72));}
.ori-404-sub{margin:20px 0 32px;font-size:16px;color:#cdd8e4;letter-spacing:.04em;text-shadow:0 2px 12px rgba(0,0,0,.8);}
.ori-404-actions{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;}
.ori-404-btn{padding:11px 28px;border-radius:999px;font-size:15px;text-decoration:none;transition:transform .2s,box-shadow .2s;display:inline-block;}
.ori-404-btn.primary{background:linear-gradient(90deg,#51aded,#78ce79);color:#06121a;font-weight:600;}
.ori-404-btn.ghost{border:1px solid rgba(255,255,255,.28);color:#eef4f9;background:rgba(255,255,255,.06);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);}
.ori-404-btn:hover{transform:translateY(-3px);box-shadow:0 10px 26px rgba(81,173,237,.38);color:inherit;}
.ori-404-motes{position:absolute;inset:0;z-index:1;overflow:hidden;pointer-events:none;}
.ori-404-motes i{position:absolute;width:3px;height:3px;border-radius:50%;background:#bfe6f7;box-shadow:0 0 8px rgba(160,220,245,.85);opacity:0;animation:ori404drift 18s linear infinite;}
@keyframes ori404breathe{from{opacity:.6}to{opacity:1}}
@keyframes ori404drift{0%{transform:translate3d(0,0,0);opacity:0}12%{opacity:.8}88%{opacity:.35}100%{transform:translate3d(20px,-170px,0);opacity:0}}
@media (prefers-reduced-motion: reduce){.ori-404-glow,.ori-404-motes i{animation:none}.ori-404-motes{display:none}}
</style>
<div class="ori-404-hero">
  <img class="ori-404-bg" src="<%- url_for('/images/theme/bg-dark.webp') %>" alt="">
  <div class="ori-404-glow"></div>
  <div class="ori-404-fade"></div>
  <div class="ori-404-motes">
    <i style="left:16%;top:80%;animation-delay:-2s"></i>
    <i style="left:32%;top:90%;animation-delay:-8s"></i>
    <i style="left:54%;top:74%;animation-delay:-13s"></i>
    <i style="left:72%;top:88%;animation-delay:-5s"></i>
    <i style="left:86%;top:70%;animation-delay:-16s"></i>
  </div>
  <div class="ori-404-content">
    <p class="ori-404-eyebrow">ERR 404 / PAGE NOT FOUND</p>
    <div class="ori-404-code">404</div>
    <p class="ori-404-sub">页面走丢了，要不要回主页看看？</p>
    <div class="ori-404-actions">
      <a class="ori-404-btn primary" href="<%- url_for() %>">返回主页</a>
      <a class="ori-404-btn ghost" href="javascript:history.go(-1)">返回上页</a>
    </div>
  </div>
</div>
`;

function apply() {
  if (hexo.theme && typeof hexo.theme.setView === 'function') {
    hexo.theme.setView('_pages/404.ejs', TEMPLATE);
  }
}

hexo.extend.filter.register('before_generate', apply);
hexo.extend.filter.register('after_init', apply);
