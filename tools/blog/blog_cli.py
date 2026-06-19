from __future__ import annotations

import argparse
import sys

from blog_core import BlogWorkflow, iter_lines, open_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Hexo blog workflow helper")
    parser.add_argument(
        "action",
        choices=["status", "check-env", "new", "import", "sync", "build", "preview", "publish", "deploy-hk", "all", "open-vault"],
    )
    parser.add_argument("--title", help="Post title for the new action")
    args = parser.parse_args()

    workflow = BlogWorkflow()

    try:
        if args.action == "status":
            print(iter_lines(workflow.status_lines()))
        elif args.action == "check-env":
            print(iter_lines(workflow.environment_report()))
        elif args.action == "new":
            title = args.title or input("Post title: ")
            path = workflow.create_post(title, open_after=True)
            print(f"Created: {path}")
        elif args.action == "import":
            posts, assets = workflow.import_to_obsidian(print)
            print(f"Imported {posts} post(s) and {assets} asset(s).")
        elif args.action == "sync":
            posts, drafts, assets = workflow.sync_to_hexo(print)
            print(f"Synced {posts} post(s), skipped {drafts} draft(s), copied {assets} asset(s).")
        elif args.action == "build":
            workflow.build(print)
        elif args.action == "preview":
            workflow.stream_command(["npm", "run", "server", "--", "-p", str(workflow.config.preferred_preview_port)], print)
        elif args.action == "publish":
            workflow.publish_all_targets(print)
        elif args.action == "deploy-hk":
            workflow.deploy_hk(print)
        elif args.action == "all":
            posts, drafts, assets = workflow.all(print)
            print(f"Synced {posts} post(s), skipped {drafts} draft(s), copied {assets} asset(s).")
        elif args.action == "open-vault":
            open_path(workflow.require_vault())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
