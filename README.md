# Campus Copilot

Campus Copilot uses scheduled GitHub Actions as its backend, runs the configured Hermes model through Ollama during each workflow run, and can deliver daily briefs and deadline reminders to Telegram. Your laptop does not need to be on when the workflow runs.

## What it does

- At **07:30 Asia/Kolkata**, checks Google Classroom (or the configured IMAP fallback), scores new job listings, and sends the daily brief.
- Every **15 minutes**, checks Telegram for personal reminder messages and forwards new Classroom notification emails.
- Every **2 hours**, checks Google Classroom for overdue assignments or deadlines within 24 hours. Reminder messages label items **OVERDUE**, **URGENT** (within 3 hours), **HIGH** (within 6 hours), or **DUE SOON** (within 24 hours).
- On demand, a manual workflow request runs Hermes coding or study help and sends the response to Telegram.
- Uses **Hermes 3 3B through Ollama** on a temporary GitHub-hosted runner. The model is cached between runs when GitHub's cache is available.
- Uses **Telegram** for phone and desktop notifications. Telegram delivers messages; GitHub Actions runs the automation.
- Makes no Claude or Anthropic API calls.
- Caches the SQLite memory between workflow runs to reduce repeated job alerts and retain job feedback. GitHub cache retention and availability apply.

The scheduled runner starts only for a workflow run; this is not a continuously running server. GitHub may delay scheduled workflows, and GitHub plan usage, repository activity, runner availability, and cache limits apply. Scheduled workflows may be disabled by GitHub after prolonged repository inactivity. Personal reminders and email-deduplication state use the GitHub Actions cache, so cache eviction can lose that state. Deadline checks do not start Ollama, avoiding model startup on those runs. The first daily or coding/study run may take longer while Hermes downloads.

## Set up GitHub Actions

### 1. Push the project to GitHub

Create a GitHub repository and push this project to its default branch. Keep the repository private if it contains personal project details. **Never commit `.env`, Google OAuth files, bot tokens, app passwords, or other credentials.**

The workflow is [`.github/workflows/campus-copilot.yml`](.github/workflows/campus-copilot.yml). GitHub Actions must be enabled for the repository. Scheduled workflows run from the default branch.

### 2. Create a Telegram bot

In Telegram, chat with **@BotFather**, create a bot, and save its token. Open the bot's chat from each device where you want notifications and press Start. Obtain the chat ID for the destination chat (a private chat or a group where the bot is present).

Add these repository secrets under **Settings → Secrets and variables → Actions → New repository secret**:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Treat the bot token like a password. Do not paste it into source code or workflow logs.

### 3. Configure academic data

For Google Classroom, authorize on your own computer:

1. Create a Google OAuth Desktop client and save its JSON as `secrets/credentials.json`.
2. Copy `.env.example` to `.env`, install requirements locally, and run `python -m campus_copilot auth`.
3. Add the complete contents of `secrets/credentials.json` as the GitHub Actions secret `GOOGLE_CREDENTIALS_JSON`.
4. Add the complete contents of `secrets/token.json` as the GitHub Actions secret `GOOGLE_TOKEN_JSON`.

The workflow materializes these secret values as temporary files for its run. The Google refresh token must remain valid and its configured scopes must include Classroom access. `CALENDAR_SYNC` is controlled by the repository's configuration/environment; Google Calendar event creation also requires the Calendar scope.

If Google OAuth is unavailable for your university account, configure these Actions secrets for the IMAP fallback instead:

- `IMAP_HOST` (optional; defaults to `imap.gmail.com`)
- `IMAP_USER`
- `IMAP_PASS` (use an app password where applicable)

The 15-minute workflow also checks this inbox and forwards new Classroom notification emails to Telegram. It ignores mail already present the first time polling is enabled. The email fallback forwards the email subject and a short plain-text excerpt; it cannot reliably reconstruct Classroom assignment status or exact due dates, so the separate 2-hour assignment-deadline check needs working Google Classroom API access.

Your university may disable IMAP or app passwords. If email access is blocked, use the email notifications already delivered to your inbox; automated forwarding from Campus Copilot will not work until IMAP access is available.

### 4. Optional delivery channels

Telegram is enough for notifications on multiple devices. To also use other existing channels, add the matching secrets:

- Email: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
- WhatsApp via Twilio: `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_WA_FROM`, `TWILIO_WA_TO`
- Notion: `NOTION_TOKEN`, `NOTION_DATABASE_ID`

Leave unused secrets unset. GitHub Actions injects configured secrets as environment variables at runtime.

### 5. Send personal reminders to your Telegram bot

After the new workflow is published and the Telegram secrets are configured, send your bot a message like:

```text
Remind me tomorrow at 5:30 PM to call Maya
```

Campus Copilot confirms and stores the one-time reminder, then messages you when it is due. Times use the timezone in `config.yaml` (`Asia/Kolkata` by default); if you omit a time, it uses 09:00. Send `/list` to see pending reminders, `/cancel ID` to cancel one, or `/help` for instructions. The scheduled workflow checks approximately every 15 minutes, but GitHub can delay it. Do not send secrets, passwords, or private credentials to the bot.

### 6. Ask for coding or study help when needed

Open the repository's **Actions → Campus Copilot → Run workflow** form:

1. Select `assist` as the task.
2. Choose `coding` or `study`.
3. Enter your question/request.
4. Start the workflow and read Hermes's response in Telegram.

This is an on-demand workflow, not a live Telegram chat bot. You start it from GitHub Actions; GitHub runs Hermes and Telegram delivers the answer. It needs the Telegram secrets and may take longer on the first run while the model is downloaded.

### 7. Test Telegram notifications

Open **Actions → Campus Copilot → Run workflow**, select `telegram-test`, then start the run. It sends one short test message without starting Ollama. If the action fails, confirm that both Telegram repository secrets are set and that you started a chat with your bot.

### 8. Test and monitor

In the repository, open **Actions → Campus Copilot → Run workflow**, select `daily` or `reminder`, and start the run. Inspect its logs in the Actions tab. Do not add commands that print environment variables or secret values.

Scheduled jobs use UTC:

- `0 2 * * *` UTC = 07:30 Asia/Kolkata daily brief
- `*/15 * * * *` UTC = Telegram and Classroom email poll (about every 15 minutes)
- `30 0-22/2 * * *` UTC = deadline check every two hours (06:00, 08:00, ..., 04:00 Asia/Kolkata)

To change these times, edit the cron expressions in the workflow. GitHub Actions cron uses UTC.

## Local development

1. Create and activate a Python virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Install Ollama and run `ollama pull hermes3:8b`.
4. Copy `.env.example` to `.env`. Local Ollama defaults to `http://localhost:11434`.
5. Configure `config.yaml`, then try `python -m campus_copilot run`.

Useful local commands:

```sh
python -m campus_copilot run
python -m campus_copilot remind
python -m campus_copilot ask "why is my Java stream null?"
python -m campus_copilot study hints "Normalise this schema to 3NF: ..."
python -m campus_copilot pa "remind me to submit DBMS record Friday 6pm"
python -m campus_copilot feedback a1b2c3d4 up
```

## What task information it currently uses

The personal-reminder feature supports one-time reminders, listing pending reminders, and cancelling them. It is not a full academic planner and does not support recurring reminders yet.

## Data sources

- Google Classroom and Calendar APIs, or IMAP Classroom notification emails.
- Public Greenhouse, Lever, and Remotive job APIs. It does not scrape LinkedIn or Naukri.
- SQLite stores seen jobs and feedback in a GitHub Actions cache. Cache availability/retention is controlled by GitHub; if it expires or is evicted, previously seen jobs may be reported again.
