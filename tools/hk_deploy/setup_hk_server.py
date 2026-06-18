from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = TOOL_ROOT / "hk_deploy.config.json"
NGINX_CONF_PATH = TOOL_ROOT / "nginx-ori2333-blog.conf"


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
    return (
        "set -e; "
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
    domain_args = " ".join(f"-d {shell_quote(domain)}" for domain in domains)
    email = str(cfg.get("certbotEmail", "")).strip()
    email_args = f"--email {shell_quote(email)}" if email else "--register-unsafely-without-email"
    return (
        "if ! command -v certbot >/dev/null 2>&1; then "
        "echo 'certbot is not installed; HTTPS was not configured' >&2; exit 1; "
        "fi; "
        "certbot --nginx --non-interactive --agree-tos "
        f"{email_args} {domain_args} --redirect --expand; "
        "nginx -t; "
        "if command -v systemctl >/dev/null 2>&1; then systemctl reload nginx || systemctl restart nginx; "
        "else nginx -s reload || nginx; fi"
    )


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
