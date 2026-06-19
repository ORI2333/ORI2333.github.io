from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = TOOL_ROOT / "hk_deploy.config.json"
NGINX_CONF_PATH = TOOL_ROOT / "nginx-ori2333-blog.conf"
CF_IPV4_RANGES = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
]
CF_IPV6_RANGES = [
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
]


def main() -> int:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    validate_config(cfg)
    remote = f"{cfg['user']}@{cfg['host']}"
    ssh_base = ["ssh", "-p", str(cfg["port"]), *cfg.get("sshOptions", [])]
    scp_base = ["scp", "-P", str(cfg["port"]), *cfg.get("sshOptions", [])]

    with tempfile.TemporaryDirectory() as tmp:
        rendered = Path(tmp) / "ori2333-blog.conf"
        rendered.write_text(render_nginx_conf(cfg), encoding="utf-8")
        run([*ssh_base, remote, remote_setup_script(cfg)])
        run([*scp_base, str(rendered), f"{remote}:/tmp/ori2333-blog.conf"])
        run([*ssh_base, remote, remote_enable_nginx_script(cfg)])

    print(f"Server prepared. Test: {cfg.get('publicUrl', '').strip() or cfg['nginxServerName']}")
    return 0


def validate_config(cfg: dict) -> None:
    server_name = str(cfg.get("nginxServerName", "")).strip()
    if not server_name or "REPLACE_WITH_YOUR_DOMAIN" in server_name or server_name == "_":
        raise RuntimeError("请先把 tools/hk_deploy/hk_deploy.config.json 里的 nginxServerName 改成真实域名。")
    if int(cfg.get("nginxListen", 80)) == 80 and server_name == "_":
        raise RuntimeError("监听 80 时必须使用明确域名，避免接管服务器默认站点。")


def render_nginx_conf(cfg: dict) -> str:
    template = NGINX_CONF_PATH.read_text(encoding="utf-8")
    return (
        template.replace("listen 8088;", f"listen {cfg['nginxListen']};")
        .replace("server_name _;", f"server_name {cfg['nginxServerName']};")
        .replace("root /var/www/ori2333-blog;", f"root {cfg['remoteRoot']};")
    )


def remote_setup_script(cfg: dict) -> str:
    remote_root = shell_quote(cfg["remoteRoot"])
    return (
        "set -e; "
        f"mkdir -p {remote_root}; "
        "if command -v nginx >/dev/null 2>&1; then exit 0; fi; "
        "if command -v apt-get >/dev/null 2>&1; then apt-get update && apt-get install -y nginx; "
        "elif command -v yum >/dev/null 2>&1; then yum install -y nginx; "
        "elif command -v dnf >/dev/null 2>&1; then dnf install -y nginx; "
        "else echo 'nginx is not installed and no supported package manager was found' >&2; exit 1; fi"
    )


def remote_enable_nginx_script(cfg: dict) -> str:
    site_file = shell_quote(site_file_name(cfg))
    real_ip_conf = "\n".join(
        [*(f"set_real_ip_from {cidr};" for cidr in CF_IPV4_RANGES), *(f"set_real_ip_from {cidr};" for cidr in CF_IPV6_RANGES)],
    )
    return (
        "set -e; "
        "cat > /etc/nginx/conf.d/00-ori-blog-log-format.conf <<'EOF'\n"
        f"{real_ip_conf}\n"
        "real_ip_header CF-Connecting-IP;\n"
        "real_ip_recursive on;\n"
        "log_format ori_blog_main '$remote_addr - $remote_user [$time_local] \"$request\" '\n"
        "                         '$status $body_bytes_sent \"$http_referer\" \"$http_user_agent\"';\n"
        "EOF\n"
        "if [ -d /etc/nginx/conf.d ]; then "
        f"mv /tmp/ori2333-blog.conf /etc/nginx/conf.d/{site_file}; "
        "elif [ -d /etc/nginx/sites-available ]; then "
        f"mv /tmp/ori2333-blog.conf /etc/nginx/sites-available/{site_file}; "
        f"ln -sf /etc/nginx/sites-available/{site_file} /etc/nginx/sites-enabled/{site_file}; "
        "else echo 'Unsupported nginx layout' >&2; exit 1; fi; "
        "nginx -t; "
        "if command -v systemctl >/dev/null 2>&1; then systemctl enable nginx >/dev/null 2>&1 || true; systemctl reload nginx || systemctl restart nginx; "
        "else nginx -s reload || nginx; fi; "
        f"{remote_https_script(cfg)}"
    )


def remote_https_script(cfg: dict) -> str:
    if not cfg.get("enableHttps", False):
        return "true"

    domains = [
        domain
        for domain in str(cfg["nginxServerName"]).split()
        if domain and domain != "_"
    ]
    primary = domains[0]
    primary_quoted = shell_quote(primary)
    domain_args = " ".join(f"-d {shell_quote(domain)}" for domain in domains)
    email = str(cfg.get("certbotEmail", "")).strip()
    email_args = f"--email {shell_quote(email)}" if email else "--register-unsafely-without-email"
    return (
        "if ! command -v certbot >/dev/null 2>&1; then "
        "echo 'certbot is not installed; HTTPS was not configured' >&2; exit 1; "
        "fi; "
        f"if [ -f /etc/letsencrypt/live/{primary_quoted}/fullchain.pem ] "
        f"&& [ -f /etc/letsencrypt/live/{primary_quoted}/privkey.pem ]; then "
        f"python3 - <<'PY'\n{nginx_ssl_patch_script(primary)}\nPY\n"
        "else "
        "certbot --nginx --non-interactive --agree-tos "
        f"{email_args} {domain_args} --redirect --expand; "
        "fi; "
        "nginx -t; "
        "if command -v systemctl >/dev/null 2>&1; then systemctl reload nginx || systemctl restart nginx; "
        "else nginx -s reload || nginx; fi"
    )


def nginx_ssl_patch_script(primary_domain: str) -> str:
    conf_path = f"/etc/nginx/conf.d/{primary_domain}.conf"
    cert_path = f"/etc/letsencrypt/live/{primary_domain}/fullchain.pem"
    key_path = f"/etc/letsencrypt/live/{primary_domain}/privkey.pem"
    return f"""from pathlib import Path
path = Path({conf_path!r})
text = path.read_text(encoding="utf-8")
if "listen 443 ssl" not in text:
    text = text.replace("listen 80;", "listen 80;\\n    listen 443 ssl http2;", 1)
if "ssl_certificate " not in text:
    marker = "\\n\\n    root "
    ssl = "\\n    ssl_certificate {cert_path};\\n    ssl_certificate_key {key_path};\\n    include /etc/letsencrypt/options-ssl-nginx.conf;\\n    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;\\n"
    text = text.replace(marker, ssl + marker, 1)
path.write_text(text, encoding="utf-8")
"""


def site_file_name(cfg: dict) -> str:
    primary = str(cfg["nginxServerName"]).split()[0]
    return f"{primary}.conf"


def run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
