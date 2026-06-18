from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("hk_deploy.config.json")


REMOTE_SCRIPT = r"""
set -e
echo "== hostname =="
hostname || true
echo
echo "== listening ports =="
(ss -ltnp || netstat -ltnp) 2>/dev/null | sed -n '1,120p' || true
echo
echo "== nginx server_name/listen =="
if [ -d /etc/nginx ]; then
  grep -RHE "^\s*(server_name|listen)\s+" /etc/nginx 2>/dev/null | sed -n '1,200p' || true
fi
echo
echo "== caddy domains =="
if [ -d /etc/caddy ]; then
  grep -RHE "^[A-Za-z0-9_.-]+\.[A-Za-z]{2,}|^:[0-9]+" /etc/caddy 2>/dev/null | sed -n '1,120p' || true
fi
echo
echo "== apache server names =="
if [ -d /etc/apache2 ] || [ -d /etc/httpd ]; then
  grep -RHE "^\s*(ServerName|ServerAlias|VirtualHost)\s+" /etc/apache2 /etc/httpd 2>/dev/null | sed -n '1,160p' || true
fi
echo
echo "== docker published ports =="
if command -v docker >/dev/null 2>&1; then
  docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Image}}" 2>/dev/null || true
fi
"""


def main() -> int:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    remote = f"{cfg['user']}@{cfg['host']}"
    command = ["ssh", "-p", str(cfg["port"]), *cfg.get("sshOptions", []), remote, REMOTE_SCRIPT]
    print("$ " + " ".join(command[:8]) + " ...")
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
