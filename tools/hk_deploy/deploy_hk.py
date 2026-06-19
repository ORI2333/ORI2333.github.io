from __future__ import annotations

import json
import os
import html
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("hk_deploy.config.json")
HEXO_HK_CONFIG_PATH = Path(__file__).with_name("_config.hk.yml")


def main() -> int:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    apply_env_overrides(cfg)
    validate_config(cfg)
    public_dir = REPO_ROOT / "public"

    npm = npm_executable()
    run([npm, "run", "clean"])
    run([hexo_executable(), "--config", f"_config.yml,{relative_to_repo(HEXO_HK_CONFIG_PATH)}", "generate"])
    rewrite_hk_asset_paths(public_dir, str(cfg.get("hkBlogPath", "/blog/")))
    write_gateway_page(cfg, public_dir)
    write_root_verification_files(cfg, public_dir)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "ori2333-blog.tar.gz"
        make_archive(public_dir, archive)
        remote = remote_target(cfg)

        ssh_base = ssh_command(cfg)
        scp_base = scp_command(cfg)

        run([*ssh_base, remote, remote_prepare_script(cfg)])
        run([*scp_base, str(archive), f"{remote}:{cfg['remoteTmp']}"])
        run([*ssh_base, remote, remote_extract_script(cfg)])

    print(f"Deployed to {public_url(cfg)}")
    return 0


def validate_config(cfg: dict) -> None:
    server_name = str(cfg.get("nginxServerName", "")).strip()
    public_url_value = str(cfg.get("publicUrl", "")).strip()
    if not server_name or "REPLACE_WITH_YOUR_DOMAIN" in server_name or server_name == "_":
        raise RuntimeError("请先把 tools/hk_deploy/hk_deploy.config.json 里的 nginxServerName 改成真实域名。")
    if "REPLACE_WITH_YOUR_DOMAIN" in public_url_value:
        raise RuntimeError("请先把 tools/hk_deploy/hk_deploy.config.json 里的 publicUrl 改成真实访问地址。")


def apply_env_overrides(cfg: dict) -> None:
    env_map = {
        "HK_HOST": "host",
        "HK_PORT": "port",
        "HK_USER": "user",
        "HK_REMOTE_ROOT": "remoteRoot",
        "HK_REMOTE_TMP": "remoteTmp",
        "HK_PUBLIC_URL": "publicUrl",
        "HK_BLOG_PATH": "hkBlogPath",
    }
    for env_name, key in env_map.items():
        value = os.environ.get(env_name)
        if value:
            cfg[key] = int(value) if key == "port" else value

    key_path = os.environ.get("HK_SSH_KEY_PATH")
    if key_path:
        key_path = str(Path(key_path).expanduser())
        cfg["sshOptions"] = [
            "-i",
            key_path,
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]


def public_url(cfg: dict) -> str:
    value = str(cfg.get("publicUrl", "")).strip()
    if value:
        return value
    scheme = "http"
    port = int(cfg.get("nginxListen", 80))
    suffix = "" if port in (80, 443) else f":{port}"
    return f"{scheme}://{cfg['nginxServerName']}{suffix}/"


def run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def npm_executable() -> str:
    found = shutil.which("npm.cmd") or shutil.which("npm")
    if found:
        return found

    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "npm.cmd",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "nodejs" / "npm.cmd",
        Path("E:/Program Files/nodejs/npm.cmd"),
        Path("D:/Program Files/nodejs/npm.cmd"),
        Path("C:/Program Files/nodejs/npm.cmd"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise RuntimeError("找不到 npm。请确认 Node.js 已安装，或把 npm.cmd 加入 PATH。")


def hexo_executable() -> str:
    suffix = ".cmd" if sys.platform.startswith("win") else ""
    candidate = REPO_ROOT / "node_modules" / ".bin" / f"hexo{suffix}"
    if candidate.exists():
        return str(candidate)
    found = shutil.which(f"hexo{suffix}") or shutil.which("hexo")
    if found:
        return found
    raise RuntimeError("找不到 Hexo。请先运行 npm install。")


def relative_to_repo(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def write_gateway_page(cfg: dict, public_dir: Path) -> None:
    public_dir.mkdir(parents=True, exist_ok=True)
    index_path = public_dir / "index.html"
    public_url_value = str(cfg.get("publicUrl", "https://blog.orixx.xyz/")).rstrip("/") + "/"
    hk_blog_path = normalized_path(str(cfg.get("hkBlogPath", "/blog/")))
    hk_blog_url = public_url_value.rstrip("/") + hk_blog_path
    edge_url = str(cfg["edgeOneUrl"])
    github_url = str(cfg["githubPagesUrl"])
    index_path.write_text(
        gateway_html(
            edge_url=edge_url,
            hk_url=hk_blog_url,
            github_url=github_url,
            hk_blog_path=hk_blog_path,
        ),
        encoding="utf-8",
    )


def write_root_verification_files(cfg: dict, public_dir: Path) -> None:
    public_dir.mkdir(parents=True, exist_ok=True)
    for item in cfg.get("rootVerificationFiles", []):
        name = str(item.get("name", "")).strip()
        content = str(item.get("content", ""))
        if not name or "/" in name or "\\" in name:
            raise RuntimeError(f"Invalid root verification file name: {name!r}")
        (public_dir / name).write_text(content, encoding="utf-8")


def normalized_path(value: str) -> str:
    value = "/" + value.strip("/")
    return value + "/"


def rewrite_hk_asset_paths(public_dir: Path, blog_path: str) -> None:
    blog_path = normalized_path(blog_path).rstrip("/")
    blog_public_dir = public_dir / blog_path.strip("/")
    if not blog_public_dir.exists():
        raise RuntimeError(f"Missing HK blog output: {blog_public_dir}")

    replacements = {
        'href="/images/': f'href="{blog_path}/images/',
        'src="/images/': f'src="{blog_path}/images/',
        'url(/images/': f'url({blog_path}/images/',
        "url('/images/": f"url('{blog_path}/images/",
        'url("/images/': f'url("{blog_path}/images/',
        'href="/icons/': f'href="{blog_path}/icons/',
        'src="/icons/': f'src="{blog_path}/icons/',
        'url(/icons/': f'url({blog_path}/icons/',
        "url('/icons/": f"url('{blog_path}/icons/",
        'url("/icons/': f'url("{blog_path}/icons/',
    }
    for path in blog_public_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".html", ".css", ".js", ".json"}:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        updated = content
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != content:
            path.write_text(updated, encoding="utf-8")


def gateway_html(edge_url: str, hk_url: str, github_url: str, hk_blog_path: str) -> str:
    avatar_path = f"{hk_blog_path}images/theme/头像.jpg"
    dark_bg_path = f"{hk_blog_path}images/theme/bg-dark.webp"
    light_bg_path = f"{hk_blog_path}images/theme/bg-light.webp"
    cards = [
        {
            "key": "hk",
            "title_zh": "稳定访问（香港站点）",
            "title_en": "Stable Access (Hong Kong)",
            "label_zh": "推荐入口",
            "label_en": "Recommended",
            "desc_zh": "由香港服务器托管，兼顾国内外网络环境，适合作为日常阅读入口。",
            "desc_en": "Hosted on the Hong Kong server and suitable for steady everyday reading from most networks.",
            "href": hk_url,
            "meta": "blog.orixx.xyz/blog/",
            "accent": "#35cd4b",
        },
        {
            "key": "edge",
            "title_zh": "大陆优化线路",
            "title_en": "Mainland Optimized",
            "label_zh": "腾讯云 CDN 加速",
            "label_en": "Tencent Cloud CDN",
            "desc_zh": "接入腾讯云 EdgeOne/CDN 加速，适合中国大陆网络下直连较慢时切换使用。",
            "desc_en": "Accelerated through Tencent Cloud EdgeOne/CDN for smoother access from mainland China.",
            "href": edge_url,
            "meta": "edgeone.cool",
            "accent": "#51aded",
        },
        {
            "key": "github",
            "title_zh": "备用镜像",
            "title_en": "Backup Mirror",
            "label_zh": "GitHub Pages",
            "label_en": "GitHub Pages",
            "desc_zh": "适合国际网络访问，同时作为公开备份镜像，方便在其他线路不可用时继续阅读。",
            "desc_en": "A public GitHub Pages mirror for international access and a backup when other routes are unavailable.",
            "href": github_url,
            "meta": "ori2333.github.io",
            "accent": "#fdbc40",
        },
    ]
    card_html = "\n".join(gateway_card(card) for card in cards)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="ORI2333's Blog access gateway">
  <title>ORI2333's Blog - 选择访问站点</title>
  <link rel="icon" href="{html.escape(avatar_path, quote=True)}">
  <style>
    :root {{
      color-scheme: dark light;
      --text: #f6f8fb;
      --muted: #b9c3d1;
      --line: rgba(255, 255, 255, .18);
      --panel: rgba(14, 22, 34, .72);
      --panel-strong: rgba(18, 28, 44, .9);
      --page-bg: #101827;
      --page-image: url("{html.escape(dark_bg_path, quote=True)}");
      --veil-a: rgba(8, 13, 24, .94);
      --veil-b: rgba(16, 24, 39, .74);
      --veil-c: rgba(14, 30, 44, .9);
      --glow: rgba(81, 173, 237, .22);
      --arrow-text: #07111e;
      --blue: #51aded;
      --green: #35cd4b;
      --amber: #fdbc40;
    }}
    :root[data-theme="light"] {{
      color-scheme: light;
      --text: #172033;
      --muted: #516173;
      --line: rgba(23, 32, 51, .15);
      --panel: rgba(255, 255, 255, .76);
      --panel-strong: rgba(255, 255, 255, .94);
      --page-bg: #f5f7fb;
      --page-image: url("{html.escape(light_bg_path, quote=True)}");
      --veil-a: rgba(245, 247, 251, .92);
      --veil-b: rgba(241, 246, 252, .76);
      --veil-c: rgba(234, 241, 247, .88);
      --glow: rgba(81, 173, 237, .2);
      --arrow-text: #07111e;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background: var(--page-bg) var(--page-image) center / cover fixed no-repeat;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      background:
        linear-gradient(120deg, var(--veil-a), var(--veil-b) 48%, var(--veil-c)),
        radial-gradient(circle at 78% 20%, var(--glow), transparent 32%);
      pointer-events: none;
    }}
    main {{
      position: relative;
      min-height: 100vh;
      display: grid;
      align-items: center;
      padding: 42px 22px;
    }}
    .shell {{
      width: min(1080px, 100%);
      margin: 0 auto;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 32px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 18px;
      margin-bottom: 32px;
    }}
    .controls {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
    }}
    .brand img {{
      width: 58px;
      height: 58px;
      border-radius: 50%;
      border: 2px solid rgba(255, 255, 255, .78);
      box-shadow: 0 10px 28px rgba(0, 0, 0, .26);
      object-fit: cover;
    }}
    .brand span {{
      display: block;
      color: var(--muted);
      font-size: 14px;
    }}
    .theme-toggle,
    .lang-toggle {{
      flex: 0 0 auto;
      min-width: 44px;
      height: 38px;
      display: inline-grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--text);
      background: var(--panel);
      cursor: pointer;
      box-shadow: 0 12px 28px rgba(0, 0, 0, .18);
    }}
    .theme-toggle:hover,
    .lang-toggle:hover {{
      background: var(--panel-strong);
    }}
    h1 {{
      margin: 0;
      font-size: 34px;
      line-height: 1.16;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .intro {{
      width: min(760px, 100%);
      margin-bottom: 30px;
    }}
    .intro p {{
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.8;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin: 22px 0 30px;
    }}
    .recommend {{
      min-height: 40px;
      padding: 0 15px;
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--text);
      background: var(--panel);
      cursor: pointer;
      font: inherit;
    }}
    .recommend:hover {{
      background: var(--panel-strong);
    }}
    .recommend-result {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }}
    .card {{
      position: relative;
      min-height: 230px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 22px;
      color: var(--text);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 22px 50px rgba(0, 0, 0, .28);
      overflow: hidden;
    }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 4px;
      background: var(--accent);
    }}
    .card:hover {{
      transform: translateY(-2px);
      border-color: rgba(255, 255, 255, .32);
      background: var(--panel-strong);
    }}
    .card.recommended {{
      border-color: var(--accent);
      box-shadow: 0 24px 58px rgba(0, 0, 0, .32), 0 0 0 1px var(--accent) inset;
    }}
    .card, .card:hover {{
      transition: transform .2s ease, border-color .2s ease, background .2s ease;
    }}
    .card h2 {{
      margin: 0;
      font-size: 21px;
      line-height: 1.3;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .label {{
      display: inline-flex;
      width: fit-content;
      margin-bottom: 16px;
      padding: 4px 9px;
      border: 1px solid var(--accent);
      border-radius: 999px;
      color: var(--accent);
      background: rgba(255, 255, 255, .06);
      font-size: 12px;
    }}
    .card p {{
      margin: 12px 0 18px;
      color: var(--muted);
      line-height: 1.72;
      font-size: 14px;
    }}
    .open {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      color: var(--text);
      text-decoration: none;
      font-size: 14px;
    }}
    .open strong {{
      overflow-wrap: anywhere;
      font-weight: 500;
      color: var(--text);
    }}
    .arrow {{
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: var(--accent);
      color: var(--arrow-text);
      font-weight: 700;
    }}
    .note {{
      margin-top: 22px;
      color: rgba(246, 248, 251, .68);
      font-size: 13px;
    }}
    @media (max-width: 820px) {{
      main {{ align-items: start; padding-top: 34px; }}
      .topbar {{ align-items: flex-start; }}
      .controls {{ margin-top: 2px; }}
      .grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 29px; }}
      .card {{ min-height: 190px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="shell" aria-labelledby="page-title">
      <div class="topbar">
        <div class="brand">
          <img src="{html.escape(avatar_path, quote=True)}" alt="ORI2333">
          <div>
            <h1 id="page-title">ORI2333's Blog</h1>
            <span data-i18n="subtitle">选择一条适合当前网络环境的阅读线路</span>
          </div>
        </div>
        <div class="controls" aria-label="页面设置">
          <button class="lang-toggle" type="button" aria-label="Switch language" title="Switch language">EN</button>
          <button class="theme-toggle" type="button" aria-label="切换黑白主题" title="切换黑白主题">☾</button>
        </div>
      </div>
      <div class="intro">
        <p data-i18n="intro">这里提供同一份博客内容的多个访问线路。如果当前网络加载较慢，可以切换到另一条线路继续阅读。</p>
      </div>
      <div class="actions">
        <button class="recommend" type="button" data-i18n="recommend">自动推荐线路</button>
        <span class="recommend-result" data-i18n="recommendHint">根据当前网络自动判断更适合的访问入口。</span>
      </div>
      <div class="grid">
        {card_html}
      </div>
      <p class="note" data-i18n="note">提示：如果某个入口加载慢，切换到另一个线路即可。</p>
    </section>
  </main>
  <script>
    (function () {{
      var root = document.documentElement;
      var key = "ori_blog_gateway_theme";
      var button = document.querySelector(".theme-toggle");
      function apply(theme) {{
        root.dataset.theme = theme;
        if (button) button.textContent = theme === "light" ? "☀" : "☾";
      }}
      var saved = localStorage.getItem(key);
      var initial = saved || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
      apply(initial);
      if (button) {{
        button.addEventListener("click", function () {{
          var next = root.dataset.theme === "light" ? "dark" : "light";
          localStorage.setItem(key, next);
          apply(next);
        }});
      }}
    }})();
    (function () {{
      var root = document.documentElement;
      var langKey = "ori_blog_gateway_lang";
      var langButton = document.querySelector(".lang-toggle");
      var recommendButton = document.querySelector(".recommend");
      var recommendResult = document.querySelector(".recommend-result");
      var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
      var text = {{
        zh: {{
          subtitle: "选择一条适合当前网络环境的阅读线路",
          intro: "这里提供同一份博客内容的多个访问线路。如果当前网络加载较慢，可以切换到另一条线路继续阅读。",
          recommend: "自动推荐线路",
          recommendHint: "根据当前网络自动判断更适合的访问入口。",
          checking: "正在检测当前网络...",
          recommended: "推荐：",
          fallbackEdge: "检测服务暂不可用，已根据浏览器语言和时区给出保守建议。",
          fallbackHk: "检测服务暂不可用，建议先使用香港站点；如果加载慢再切换线路。",
          error: "暂时无法完成自动检测，请手动选择访问线路。",
          note: "提示：如果某个入口加载慢，切换到另一个线路即可。"
        }},
        en: {{
          subtitle: "Choose the best route for your current network",
          intro: "This page offers multiple routes to the same blog. If one route loads slowly, switch to another and keep reading.",
          recommend: "Recommend route",
          recommendHint: "Automatically choose a route based on your current network.",
          checking: "Checking your network...",
          recommended: "Recommended: ",
          fallbackEdge: "The detection service is unavailable, so this is a conservative suggestion based on language and timezone.",
          fallbackHk: "The detection service is unavailable. Try the Hong Kong route first, then switch if it is slow.",
          error: "Automatic detection is unavailable right now. Please choose a route manually.",
          note: "Tip: if one route is slow, switch to another route."
        }}
      }};
      function currentLang() {{
        return root.dataset.lang === "en" ? "en" : "zh";
      }}
      function applyLang(lang) {{
        root.dataset.lang = lang;
        if (langButton) langButton.textContent = lang === "zh" ? "EN" : "中";
        document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
        document.querySelectorAll("[data-i18n]").forEach(function (node) {{
          var key = node.getAttribute("data-i18n");
          if (text[lang][key]) node.textContent = text[lang][key];
        }});
        cards.forEach(function (card) {{
          card.querySelector("[data-title]").textContent = card.getAttribute("data-title-" + lang);
          card.querySelector("[data-label]").textContent = card.getAttribute("data-label-" + lang);
          card.querySelector("[data-desc]").textContent = card.getAttribute("data-desc-" + lang);
        }});
      }}
      function setRecommended(target, reason) {{
        var lang = currentLang();
        cards.forEach(function (card) {{
          card.classList.toggle("recommended", card.dataset.route === target);
        }});
        var card = cards.find(function (item) {{ return item.dataset.route === target; }});
        if (recommendResult && card) {{
          recommendResult.textContent = text[lang].recommended + card.getAttribute("data-title-" + lang) + (reason ? "，" + reason : "");
        }}
      }}
      function fallbackRecommend() {{
        var lang = currentLang();
        var timezone = "";
        try {{ timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; }} catch (error) {{}}
        var browserLang = (navigator.language || "").toLowerCase();
        var mainlandLike = timezone === "Asia/Shanghai" || browserLang === "zh-cn";
        setRecommended(mainlandLike ? "edge" : "hk", mainlandLike ? text[lang].fallbackEdge : text[lang].fallbackHk);
      }}
      var savedLang = localStorage.getItem(langKey) || ((navigator.language || "").toLowerCase().startsWith("zh") ? "zh" : "en");
      applyLang(savedLang);
      if (langButton) {{
        langButton.addEventListener("click", function () {{
          var next = currentLang() === "zh" ? "en" : "zh";
          localStorage.setItem(langKey, next);
          applyLang(next);
        }});
      }}
      if (recommendButton) {{
        recommendButton.addEventListener("click", function () {{
          var lang = currentLang();
          if (recommendResult) recommendResult.textContent = text[lang].checking;
          fetch("/api/recommend", {{ cache: "no-store" }})
            .then(function (res) {{ if (!res.ok) throw new Error("bad status"); return res.json(); }})
            .then(function (data) {{
              var reason = currentLang() === "en" ? (data.reason_en || data.reason || "") : (data.reason_zh || data.reason || "");
              setRecommended(data.target || "hk", reason);
            }})
            .catch(function () {{
              fallbackRecommend();
            }});
        }});
      }}
    }})();
  </script>
</body>
</html>
"""


def gateway_card(card: dict[str, str]) -> str:
    return f"""<article class="card" data-route="{html.escape(card['key'], quote=True)}" data-title-zh="{html.escape(card['title_zh'], quote=True)}" data-title-en="{html.escape(card['title_en'], quote=True)}" data-label-zh="{html.escape(card['label_zh'], quote=True)}" data-label-en="{html.escape(card['label_en'], quote=True)}" data-desc-zh="{html.escape(card['desc_zh'], quote=True)}" data-desc-en="{html.escape(card['desc_en'], quote=True)}" style="--accent: {card['accent']}">
          <div>
            <span class="label" data-label>{html.escape(card['label_zh'])}</span>
            <h2 data-title>{html.escape(card['title_zh'])}</h2>
            <p data-desc>{html.escape(card['desc_zh'])}</p>
          </div>
          <a class="open" href="{html.escape(card['href'], quote=True)}">
            <strong>{html.escape(card['meta'])}</strong>
            <span class="arrow">→</span>
          </a>
        </article>"""


def make_archive(public_dir: Path, archive: Path) -> None:
    if not public_dir.exists():
        raise RuntimeError(f"Missing build output: {public_dir}")
    with tarfile.open(archive, "w:gz") as tar:
        for path in public_dir.rglob("*"):
            tar.add(path, arcname=path.relative_to(public_dir))


def ssh_command(cfg: dict) -> list[str]:
    return ["ssh", "-p", str(cfg["port"]), *cfg.get("sshOptions", [])]


def scp_command(cfg: dict) -> list[str]:
    return ["scp", "-P", str(cfg["port"]), *cfg.get("sshOptions", [])]


def remote_target(cfg: dict) -> str:
    return f"{cfg['user']}@{cfg['host']}"


def remote_prepare_script(cfg: dict) -> str:
    remote_root = shell_quote(cfg["remoteRoot"])
    remote_tmp = shell_quote(cfg["remoteTmp"])
    return (
        "set -e; "
        f"mkdir -p {remote_root}; "
        f"rm -f {remote_tmp}; "
        "command -v tar >/dev/null"
    )


def remote_extract_script(cfg: dict) -> str:
    remote_root = shell_quote(cfg["remoteRoot"])
    remote_tmp = shell_quote(cfg["remoteTmp"])
    return (
        "set -e; "
        f"find {remote_root} -mindepth 1 -maxdepth 1 -exec rm -rf {{}} +; "
        f"tar -xzf {remote_tmp} -C {remote_root}; "
        f"rm -f {remote_tmp}"
    )


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
