# Internship Discord Bot

Small scheduled script that reads the upstream Summer 2027 internship JSON feed and posts new jobs to a Discord incoming webhook.

## Setup

1. In your Discord server, open the target channel's **Edit Channel** → **Integrations** → **Webhooks**, create a webhook, and copy its URL.
2. For local use, create a `.env` file containing your webhook URL, then run:

   ```bash
   printf 'DISCORD_WEBHOOK_URL=your-webhook-url\n' > .env
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   python main.py
   ```

   The first run records all currently matching jobs without posting them. Later runs post only unseen IDs.
3. In GitHub, open **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, name it `DISCORD_WEBHOOK_URL`, and paste the webhook URL.
4. Commit and push this project. The workflow in `.github/workflows/check_jobs.yml` runs every six hours and can also be started with **Actions** → **Check internship feed** → **Run workflow**. It commits `data/posted_jobs.json` back to the repository so IDs persist between runs.

The workflow needs repository Actions permission to write contents; the workflow declares `contents: write`. If repository settings restrict this, enable **Settings** → **Actions** → **General** → **Workflow permissions** → **Read and write permissions**.
