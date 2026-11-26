# codegolf-war

Keeps the "code.golf: Humans vs AI" dashboard live, for free.

- **GitHub Actions** (`.github/workflows/refresh.yml`) runs `scripts/build.py` about every 10 minutes. It pulls code.golf's full solutions feed, works out who leads each hole × language, and force-pushes 5 small JSON files to the repo's `data` branch.
- **A Cloudflare Worker** (`worker/`) is a tiny MCP server that hands those files to Claude. You add it to claude.ai as a custom connector, and the dashboard reads from it.
- **`ai_accounts.txt`** lists the accounts counted as AI, one per line. Edit it to move golfers between sides. The next run picks up the change.

## Setup

### 1. GitHub repo
1. Create a **public** repo named `codegolf-war`. Actions minutes are free for public repos.
2. Upload everything in this folder, keeping the folder structure. The `.github` folder is hidden on Mac and Linux, and drag-and-drop often skips it. If it's missing after the upload, use **Add file → Create new file**, type `.github/workflows/refresh.yml` as the name, and paste the file's contents.
3. **Settings → Actions → General → Workflow permissions →** choose **Read and write permissions**, then save.
4. Open the **Actions** tab. If asked, enable workflows. Open **Refresh code.golf data → Run workflow**.
5. The run takes 2–4 minutes. When it finishes, switch to the `data` branch. You should see `weekly.json`, `cells.json`, `hole_month.json`, `lang_month.json` and `meta.json`.

### 2. Cloudflare Worker (free plan)
1. Sign up at cloudflare.com (free) and install Node.js (LTS).
2. In `worker/wrangler.toml`, set `REPO = "your-github-username/codegolf-war"`.
3. In a terminal:
   ```
   cd worker
   npx wrangler login
   npx wrangler deploy
   ```
4. Wrangler prints a URL like `https://codegolf-war.<your-subdomain>.workers.dev`. Your connector URL is that URL followed by `/mcp`.

### 3. claude.ai
1. **Settings → Connectors → Add custom connector.** Name it `code.golf war` and paste the `/mcp` URL. No auth is needed.
2. Tell Claude the connector is added. Claude will switch the dashboard's data to it and add a Refresh button.

## Good to know
- GitHub pauses scheduled workflows in a repo that has no commits on its main branch for 60 days. Pushes to the `data` branch don't count. GitHub emails you first, and one click keeps it running.
- GitHub's schedule is best-effort. Runs are often a few minutes late, so in practice data updates every 10–20 minutes.
- The timeline is rebuilt from each golfer's latest submission date per cell. An earlier, longer solution that was later improved isn't in the feed, so past leads can show up later than they really happened.
- Test locally with `python scripts/build.py out`. Only the standard library is used.
