---
name: blog-workflow
description: Manage this Hexo blog's Obsidian-to-repo workflow, including creating posts from templates, syncing drafts and assets, previewing locally, and publishing through the repo scripts. Use when the user asks to write, sync, preview, publish, or automate this blog.
---

# Blog Workflow

## Use the Workflow

Use `tools/blog/blog_gui.py` as the primary human-facing entry point and `tools/blog/blog_cli.py` for automation.

- Use `New` to create a draft in the Obsidian posts folder.
- Use `Import` to seed Obsidian from the current Hexo repo.
- Use `Sync` to copy Obsidian posts and assets into `source/_posts` and `source/images/posts`.
- Use `Build` or `Preview` to validate locally.
- Use `Publish` to run the repo push flow.
- Use `All` for the full daily flow.

## Rules

- Keep Obsidian as the drafting surface.
- Keep `source/_posts` as the Hexo source of truth.
- Do not edit `public/` manually.
- Read `tools/blog/blog.config.json` for vault paths and folder names.
- Read `templates/blog-post.md` for the canonical front matter shape.
- Read `docs/blog-workflow-migration.md` when the user asks about moving to a new computer, switching environments, or debugging missing Qt/Python dependencies.
- Treat `draft: true` as a private Obsidian draft. Sync skips those posts.
- Prefer `npm run blog` for the GUI and `npm run blog:sync` style commands for direct automation.

## Reference

See [references/workflow.md](references/workflow.md) for the action map and setup notes.
