from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import html
import http.cookies
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8765
DB_PATH = Path("/var/lib/ori-blog-admin/admin.sqlite3")
INITIAL_PASSWORD_PATH = Path("/var/lib/ori-blog-admin/initial-password.txt")
ACCESS_LOG_PATH = Path("/var/log/nginx/ori-blog-access.log")
CN_CIDR_PATH = Path("/etc/nginx/geoip/cn.conf")
SESSION_COOKIE = "ori_blog_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 8
PBKDF2_ROUNDS = 260_000
STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".jpg",
    ".jpeg",
    ".gif",
    ".png",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".json",
    ".xml",
    ".txt",
}


LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<target>\S+) (?P<proto>[^"]+)" '
    r'(?P<status>\d+) (?P<size>\S+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"$'
)


def main() -> int:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ORI blog admin listening on http://{HOST}:{PORT}")
    server.serve_forever()
    return 0


class Handler(BaseHTTPRequestHandler):
    server_version = "OriBlogAdmin/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            self.send_text("ok\n")
            return
        if path == "/api/recommend":
            self.send_json(recommend_for_ip(client_ip(self)))
            return
        if path in {"/admin", "/admin/"}:
            if not self.current_user():
                self.send_html(login_page())
                return
            self.send_html(dashboard_page())
            return
        if path == "/admin/password":
            if not self.require_login():
                return
            self.send_html(password_page())
            return
        if path == "/admin/article":
            if not self.require_login():
                return
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            article = query.get("path", [""])[0]
            self.send_html(article_page(article))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        form = self.read_form()
        if path == "/admin/login":
            user = form.get("username", "")
            password = form.get("password", "")
            if verify_user(user, password):
                token = create_session(user)
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/admin/")
                self.send_header(
                    "Set-Cookie",
                    f"{SESSION_COOKIE}={token}; Path=/admin/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}",
                )
                self.end_headers()
            else:
                self.send_html(login_page("账号或密码不正确。"), status=HTTPStatus.UNAUTHORIZED)
            return
        if path == "/admin/logout":
            token = session_token(self)
            if token:
                delete_session(token)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/admin/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")
            self.end_headers()
            return
        if path == "/admin/password":
            if not self.require_login():
                return
            old = form.get("old_password", "")
            new = form.get("new_password", "")
            confirm = form.get("confirm_password", "")
            if new != confirm:
                self.send_html(password_page("两次输入的新密码不一致。"), status=HTTPStatus.BAD_REQUEST)
                return
            if len(new) < 10:
                self.send_html(password_page("新密码至少 10 位。"), status=HTTPStatus.BAD_REQUEST)
                return
            if not verify_user("admin", old):
                self.send_html(password_page("旧密码不正确。"), status=HTTPStatus.UNAUTHORIZED)
                return
            set_password("admin", new)
            self.send_html(password_page("密码已修改。"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def current_user(self) -> str | None:
        token = session_token(self)
        if not token:
            return None
        return user_for_session(token)

    def require_login(self) -> bool:
        if self.current_user():
            return True
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/admin/")
        self.end_headers()
        return False

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(body)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            "create table if not exists users (username text primary key, password_hash text not null, updated_at integer not null)"
        )
        conn.execute(
            "create table if not exists sessions (token_hash text primary key, username text not null, expires_at integer not null)"
        )
        conn.execute(
            "create table if not exists ip_cache (ip text primary key, address text not null, updated_at integer not null)"
        )
        exists = conn.execute("select 1 from users where username = 'admin'").fetchone()
        if not exists:
            password = read_initial_password()
            conn.execute(
                "insert into users (username, password_hash, updated_at) values (?, ?, ?)",
                ("admin", hash_password(password), int(time.time())),
            )


def read_initial_password() -> str:
    if INITIAL_PASSWORD_PATH.exists():
        return INITIAL_PASSWORD_PATH.read_text(encoding="utf-8").strip()
    password = secrets.token_urlsafe(18)
    INITIAL_PASSWORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    INITIAL_PASSWORD_PATH.write_text(password + "\n", encoding="utf-8")
    INITIAL_PASSWORD_PATH.chmod(0o600)
    return password


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${b64(salt)}${b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
        salt = b64decode(salt_raw)
        expected = b64decode(digest_raw)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def set_password(username: str, password: str) -> None:
    with connect() as conn:
        conn.execute(
            "update users set password_hash = ?, updated_at = ? where username = ?",
            (hash_password(password), int(time.time()), username),
        )
        conn.execute("delete from sessions where username = ?", (username,))


def verify_user(username: str, password: str) -> bool:
    with connect() as conn:
        row = conn.execute("select password_hash from users where username = ?", (username,)).fetchone()
    return bool(row and verify_password(password, row["password_hash"]))


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute("delete from sessions where expires_at < ?", (int(time.time()),))
        conn.execute(
            "insert into sessions (token_hash, username, expires_at) values (?, ?, ?)",
            (hash_token(token), username, int(time.time()) + SESSION_TTL_SECONDS),
        )
    return token


def user_for_session(token: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "select username from sessions where token_hash = ? and expires_at >= ?",
            (hash_token(token), int(time.time())),
        ).fetchone()
    return row["username"] if row else None


def delete_session(token: str) -> None:
    with connect() as conn:
        conn.execute("delete from sessions where token_hash = ?", (hash_token(token),))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_token(handler: BaseHTTPRequestHandler) -> str | None:
    raw = handler.headers.get("Cookie", "")
    cookie = http.cookies.SimpleCookie(raw)
    item = cookie.get(SESSION_COOKIE)
    return item.value if item else None


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real = handler.headers.get("X-Real-IP", "")
    if real:
        return real.strip()
    return handler.client_address[0]


def recommend_for_ip(ip: str) -> dict[str, str]:
    if is_cn_ip(ip):
        return {
            "target": "edge",
            "reason_zh": "检测到当前 IP 更接近中国大陆网络，优先推荐腾讯云 CDN 加速线路。",
            "reason_en": "Your IP appears closer to mainland China, so the Tencent Cloud CDN route is recommended.",
            "ip": ip,
        }
    return {
        "target": "hk",
        "reason_zh": "当前网络更适合优先使用香港服务器线路。",
        "reason_en": "The Hong Kong server route is recommended for your current network.",
        "ip": ip,
    }


def is_cn_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if address.is_private or address.is_loopback:
        return False
    for network in cn_networks():
        if address in network:
            return True
    return False


def cn_networks() -> list[ipaddress._BaseNetwork]:
    if not CN_CIDR_PATH.exists():
        return []
    networks = []
    for line in CN_CIDR_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cidr = line.split()[0]
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return networks


def parse_access_log() -> list[dict[str, str]]:
    if not ACCESS_LOG_PATH.exists():
        return []
    lines = tail_lines(ACCESS_LOG_PATH, 8000)
    rows: list[dict[str, str]] = []
    for line in lines:
        match = LOG_RE.match(line)
        if not match:
            continue
        row = match.groupdict()
        try:
            parsed = urllib.parse.urlparse(row["target"])
        except ValueError:
            continue
        row["path"] = urllib.parse.unquote(parsed.path or "/")
        if should_ignore_path(row["path"]):
            continue
        row["address"] = address_for_ip(row["ip"])
        rows.append(row)
    return rows


def tail_lines(path: Path, max_lines: int) -> list[str]:
    data = path.read_bytes()[-2_500_000:]
    return data.decode("utf-8", errors="replace").splitlines()[-max_lines:]


def should_ignore_path(path: str) -> bool:
    if path.startswith("/admin") or path.startswith("/api/"):
        return True
    suffix = Path(path).suffix.lower()
    return suffix in STATIC_EXTENSIONS


def is_article_path(path: str) -> bool:
    return re.match(r"^/blog/\d{4}/\d{2}/\d{2}/[^/?#]+/?$", path) is not None


def is_gateway_path(path: str) -> bool:
    return path in {"/", "/index.html"}


def address_for_ip(ip: str) -> str:
    try:
        parsed = ipaddress.ip_address(ip)
        if parsed.is_private or parsed.is_loopback:
            return "本地/内网"
    except ValueError:
        return "未知"
    now = int(time.time())
    with connect() as conn:
        row = conn.execute("select address, updated_at from ip_cache where ip = ?", (ip,)).fetchone()
        if row and now - int(row["updated_at"]) < 60 * 60 * 24 * 14:
            return row["address"]
    address = lookup_ip_address(ip)
    with connect() as conn:
        conn.execute(
            "insert or replace into ip_cache (ip, address, updated_at) values (?, ?, ?)",
            (ip, address, now),
        )
    return address


def lookup_ip_address(ip: str) -> str:
    url = "http://ip-api.com/json/" + urllib.parse.quote(ip) + "?lang=zh-CN&fields=status,country,regionName,city,query"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "未知"
    if data.get("status") != "success":
        return "未知"
    parts = [data.get("country"), data.get("regionName"), data.get("city")]
    return " / ".join(str(part) for part in parts if part) or "未知"


def dashboard_page() -> str:
    rows = parse_access_log()
    total = len(rows)
    unique_ips = len({row["ip"] for row in rows})
    gateway = [row for row in rows if is_gateway_path(row["path"])]
    articles = [row for row in rows if is_article_path(row["path"])]
    article_stats = summarize_articles(articles)
    recent = list(reversed(rows[-120:]))
    return layout(
        "访问统计",
        f"""
        <section class="summary">
          <div><strong>{total}</strong><span>总访问</span></div>
          <div><strong>{unique_ips}</strong><span>独立 IP</span></div>
          <div><strong>{len(gateway)}</strong><span>入口页访问</span></div>
          <div><strong>{len(articles)}</strong><span>文章访问</span></div>
        </section>
        <section class="panel">
          <h2>文章访问量</h2>
          <table>
            <thead><tr><th>文章路径</th><th>访问</th><th>独立 IP</th><th>最近访问</th></tr></thead>
            <tbody>{''.join(article_row(row) for row in article_stats)}</tbody>
          </table>
        </section>
        <section class="panel">
          <h2>最近访问</h2>
          <table>
            <thead><tr><th>时间</th><th>IP</th><th>地址</th><th>路径</th><th>状态</th></tr></thead>
            <tbody>{''.join(visit_row(row) for row in recent)}</tbody>
          </table>
        </section>
        """,
    )


def summarize_articles(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    for row in rows:
        path = normalize_article_path(row["path"])
        item = stats.setdefault(path, {"path": path, "count": 0, "ips": set(), "last": ""})
        item["count"] = int(item["count"]) + 1
        item["ips"].add(row["ip"])  # type: ignore[union-attr]
        item["last"] = row["time"]
    result = []
    for item in stats.values():
        result.append(
            {
                "path": item["path"],
                "count": item["count"],
                "ip_count": len(item["ips"]),  # type: ignore[arg-type]
                "last": item["last"],
            }
        )
    return sorted(result, key=lambda item: int(item["count"]), reverse=True)


def normalize_article_path(path: str) -> str:
    return path if path.endswith("/") else path + "/"


def article_page(article: str) -> str:
    rows = [row for row in parse_access_log() if normalize_article_path(row["path"]) == normalize_article_path(article)]
    recent = list(reversed(rows[-200:]))
    return layout(
        "文章访问详情",
        f"""
        <section class="panel">
          <h2>{escape(article)}</h2>
          <p class="muted">访问 {len(rows)} 次，独立 IP {len({row['ip'] for row in rows})} 个。</p>
          <table>
            <thead><tr><th>时间</th><th>IP</th><th>地址</th><th>状态</th><th>User-Agent</th></tr></thead>
            <tbody>{''.join(article_visit_row(row) for row in recent)}</tbody>
          </table>
        </section>
        """,
    )


def login_page(message: str = "") -> str:
    alert = f'<p class="alert">{escape(message)}</p>' if message else ""
    return base_page(
        "后台登录",
        f"""
        <main class="login">
          <form method="post" action="/admin/login">
            <h1>博客统计后台</h1>
            {alert}
            <label>账号<input name="username" value="admin" autocomplete="username"></label>
            <label>密码<input name="password" type="password" autocomplete="current-password"></label>
            <button type="submit">登录</button>
          </form>
        </main>
        """,
    )


def password_page(message: str = "") -> str:
    alert = f'<p class="alert ok">{escape(message)}</p>' if message else ""
    return layout(
        "修改密码",
        f"""
        <section class="panel narrow">
          {alert}
          <form method="post" action="/admin/password">
            <label>旧密码<input name="old_password" type="password" autocomplete="current-password"></label>
            <label>新密码<input name="new_password" type="password" autocomplete="new-password"></label>
            <label>确认新密码<input name="confirm_password" type="password" autocomplete="new-password"></label>
            <button type="submit">保存</button>
          </form>
        </section>
        """,
    )


def layout(title: str, body: str) -> str:
    return base_page(
        title,
        f"""
        <header>
          <div><strong>ORI 博客统计后台</strong><span>{escape(title)}</span></div>
          <nav>
            <a href="/admin/">统计</a>
            <a href="/admin/password">修改密码</a>
            <form method="post" action="/admin/logout"><button type="submit">退出</button></form>
          </nav>
        </header>
        <main>{body}</main>
        """,
    )


def base_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - ORI 博客统计后台</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif; background: #f3f6f8; color: #17212f; }}
    header {{ display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 18px 28px; background: #15202b; color: #fff; }}
    header span {{ display: block; margin-top: 4px; color: #c8d4df; font-size: 13px; }}
    nav {{ display: flex; align-items: center; gap: 12px; }}
    nav a, button {{ border: 1px solid #c9d4df; border-radius: 6px; padding: 8px 12px; background: #fff; color: #17212f; text-decoration: none; cursor: pointer; font: inherit; }}
    nav form {{ margin: 0; }}
    main {{ padding: 24px; max-width: 1180px; margin: 0 auto; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }}
    .summary div, .panel, .login form {{ background: #fff; border: 1px solid #d8e0ea; border-radius: 8px; box-shadow: 0 12px 28px rgba(20, 31, 48, .08); }}
    .summary div {{ padding: 18px; }}
    .summary strong {{ display: block; font-size: 28px; color: #176b66; }}
    .summary span, .muted {{ color: #647386; }}
    .panel {{ padding: 18px; margin-bottom: 18px; overflow-x: auto; }}
    .panel.narrow {{ max-width: 560px; }}
    h1, h2 {{ margin: 0 0 14px; letter-spacing: 0; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5ebf2; text-align: left; vertical-align: top; }}
    th {{ color: #516173; font-weight: 700; white-space: nowrap; }}
    td.path, td.ua {{ overflow-wrap: anywhere; }}
    .login {{ min-height: 100vh; display: grid; place-items: center; padding: 20px; }}
    .login form {{ width: min(420px, 100%); padding: 22px; }}
    label {{ display: grid; gap: 7px; margin: 0 0 14px; color: #516173; }}
    input {{ min-height: 38px; padding: 8px 10px; border: 1px solid #d4dde8; border-radius: 6px; font: inherit; }}
    form button[type="submit"], .login button {{ background: #176b66; border-color: #176b66; color: white; font-weight: 700; }}
    .alert {{ padding: 10px 12px; border-radius: 6px; background: #fff5ec; color: #95430d; }}
    .alert.ok {{ background: #eefaf3; color: #176b66; }}
    @media (max-width: 760px) {{ header, nav {{ align-items: flex-start; flex-direction: column; }} .summary {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>{body}</body>
</html>"""


def article_row(row: dict[str, object]) -> str:
    path = str(row["path"])
    link = "/admin/article?path=" + urllib.parse.quote(path, safe="")
    return (
        "<tr>"
        f'<td class="path"><a href="{escape(link)}">{escape(path)}</a></td>'
        f"<td>{row['count']}</td>"
        f"<td>{row['ip_count']}</td>"
        f"<td>{escape(str(row['last']))}</td>"
        "</tr>"
    )


def visit_row(row: dict[str, str]) -> str:
    return (
        "<tr>"
        f"<td>{escape(row['time'])}</td>"
        f"<td>{escape(row['ip'])}</td>"
        f"<td>{escape(row['address'])}</td>"
        f'<td class="path">{escape(row["path"])}</td>'
        f"<td>{escape(row['status'])}</td>"
        "</tr>"
    )


def article_visit_row(row: dict[str, str]) -> str:
    return (
        "<tr>"
        f"<td>{escape(row['time'])}</td>"
        f"<td>{escape(row['ip'])}</td>"
        f"<td>{escape(row['address'])}</td>"
        f"<td>{escape(row['status'])}</td>"
        f'<td class="ua">{escape(row["ua"])}</td>'
        "</tr>"
    )


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
