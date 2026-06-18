# Blog Workflow Reference

## Files

- `tools/blog/blog_gui.py` - PyQt GUI entry point
- `tools/blog/blog_cli.py` - command line entry point
- `tools/blog/blog_core.py` - shared workflow logic
- `tools/blog/blog.config.json` - vault and folder configuration
- `templates/blog-post.md` - post template
- `docs/blog-workflow-migration.md` - migration and troubleshooting guide

## Actions

- `Menu` - open the interactive selector
- `New` - create a new Obsidian draft
- `Import` - copy repo posts and images into Obsidian
- `Sync` - copy Obsidian posts and assets into Hexo
- `Build` - run `hexo clean` + `hexo generate`
- `Preview` - run the local Hexo server
- `Publish` - run `npm run push`
- `All` - sync, build, publish
- `Status` - print paths and git status
- `OpenVault` - open the configured Obsidian folder

## Setup Notes

- Put the Obsidian vault path in `tools/blog/blog.config.json` or set `BLOG_OBSIDIAN_VAULT`.
- Keep blog drafts in the configured posts folder, usually `Blog/Posts`.
- Keep attachments in the configured assets folder, usually `Blog/Assets`.
- Use `npm run blog` for the GUI or `npm run blog:sync` and friends for direct actions.
- New posts start with `draft: true`; remove it or change it to `draft: false` before syncing a post for publication.
- Covers are optional. Sync falls back to `defaultCover` when `cover` is blank or still uses the placeholder.
- The GUI can set the latest Obsidian post cover from a local image or an `http(s)` image URL.
