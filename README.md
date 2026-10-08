# Campus Copilot

Campus Copilot uses a Telegram webhook hosted on Render for direct text conversations, Supabase to store personal reminders, and scheduled GitHub Actions to deliver reminders when they are due. Your laptop does not need to be on.

## What it does

- Keeps unsolicited daily job digests off; run a daily digest manually only when you want it.
- Telegram messages reach the Render webhook directly. It can acknowledge and save a text reminder without you opening GitHub Actions.
- Every **5 minutes**, GitHub Actions checks Supabase for due personal reminders and sends a compact digest only for new actionable Classroom emails (assignments, due dates, quizzes, exams, submissions, and similar items).
- Every **2 hours**, checks Google Classroom for key deadline milestones: within 6 hours, within 1 hour, and overdue. It sends each milestone once per assignment and does not repeat the same alert every run.
- On demand, a manual workflow request runs Hermes coding or study help and sends the response to Telegram.
- Uses **Hermes 3 3B through Ollama** on a temporary GitHub-hosted runner. The model is cached between runs when GitHub's cache is available.
- Uses **Telegram** for phone and desktop notifications. Telegram delivers messages; GitHub Actions runs the automation.
- Makes no Claude or Anthropic API calls.
- Caches the SQLite memory between workflow runs to reduce repeated job alerts and retain job feedback. GitHub cache retention and availability apply.

The Render service uses its free plan, which can sleep when idle. Telegram may take longer to receive an acknowledgement while the service wakes. Due-time reminders are checked by GitHub Actions about every 5 minutes, and scheduled runs may be delayed, so delivery is not guaranteed at the exact requested minute. GitHub may disable scheduled workflows after prolonged repository inactivity; runner availability and usage limits also apply. Personal reminders, deadline-alert deduplication, and email-deduplication state are stored in Supabase. The first on-demand coding/study run may take longer while Hermes downloads.

## Set up GitHub Actions

### 1. Push the project to GitHub

Create a GitHub repository and push this project to its default branch. Keep the repository private if it contains personal project details. **Never commit `.env`, Google OAuth files, bot tokens, app passwords, or other credentials.**

The workflow is [`.github/workflows/campus-copilot.yml`](.github/workflows/campus-copilot.yml). GitHub Actions must be enabled for the repository. Scheduled workflows run from the default branch.

### 2. Create a Telegram bot

In Telegram, chat with **@BotFather**, create a bot, and save its token. Open the bot's chat from each device where you want notifications and press Start. Obtain the chat ID for the destination chat (a private chat or a group where the bot is present).

Keep the bot token private. You will enter `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as environment variables in Render and as repository secrets in GitHub.

### 3. Create a Supabase database

1. Create a Supabase project using its free plan.
2. In the Supabase SQL Editor, run [`supabase/schema.sql`](supabase/schema.sql).
3. Copy the project URL and the `service_role` secret key from the Supabase project API settings. Do not use the public `anon` key for this private bot.
4. You will add these as `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in Render and GitHub Actions. The service-role key is highly sensitive; never paste it in chat or commit it.

### 4. Deploy the Telegram bot to Render

1. Sign in to Render and choose **New → Blueprint**.
2. Connect the GitHub repository `bathlakavya/automation` and select its `main` branch. Render will read [`render.yaml`](render.yaml).
3. When prompted, provide `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`. Render generates `TELEGRAM_WEBHOOK_SECRET`.
4. Deploy the Blueprint. Wait until Render reports the service as healthy; its health check registers the Telegram webhook automatically.

The free Render service may sleep when idle, so the first reply after sleep can be delayed. Render's local filesystem is temporary; reminders live in Supabase so they survive service restarts.

### 5. Add GitHub Actions secrets

In the GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Without the Supabase secrets, GitHub's automatic due-reminder checks cannot read the saved reminders.

### 6. Configure academic data (optional)

Google Classroom OAuth is not connected yet. If Google later allows the required Classroom permission, authorize locally and store the credentials as GitHub secrets `GOOGLE_CREDENTIALS_JSON` and `GOOGLE_TOKEN_JSON`.

As an alternative, configure the GitHub Actions secrets `IMAP_USER` and `IMAP_PASS` (plus optional `IMAP_HOST`, default `imap.gmail.com`) to forward new actionable Classroom notification emails to Telegram. Routine course chatter is ignored and important new emails are grouped into a single brief digest. The first email check ignores messages already in the inbox. Email excerpts do not provide reliable exact due dates, so assignment deadline reminders require Classroom API access. University accounts may block IMAP or app passwords.

### 7. Optional delivery channels

Telegram is enough for notifications on multiple devices. To also use other existing channels, add the matching secrets:

- Email: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
- WhatsApp via Twilio: `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_WA_FROM`, `TWILIO_WA_TO`
- Notion: `NOTION_TOKEN`, `NOTION_DATABASE_ID`

Leave unused secrets unset. GitHub Actions injects configured secrets as environment variables at runtime.

### 8. Send personal reminders to your Telegram bot

After Render deploys successfully, send your bot a text message like:

```text
Remind me tomorrow at 5:30 PM to call Maya
```

The Render webhook acknowledges the message and stores the one-time reminder in Supabase. GitHub Actions checks about every 15 minutes and sends a Telegram notification when it is due; GitHub can delay that check. Times use `Asia/Kolkata` by default; if you omit the time, it uses 09:00. Send `/list` to see pending reminders, `/cancel ID` to cancel one, or `/help` for instructions. Only text reminders are supported. Do not send secrets, passwords, or private credentials to the bot.

### 9. Ask for coding or study help when needed

Open the repository's **Actions → Campus Copilot → Run workflow** form:

1. Select `assist` as the task.
2. Choose `coding` or `study`.
3. Enter your question/request.
4. Start the workflow and read Hermes's response in Telegram.

This is an on-demand workflow, not a live Telegram chat bot. You start it from GitHub Actions; GitHub runs Hermes and Telegram delivers the answer. It needs the Telegram secrets and may take longer on the first run while the model is downloaded.

### 10. Test Telegram notifications

Open **Actions → Campus Copilot → Run workflow**, select `telegram-test`, then start the run. It sends one short test message without starting Ollama. If the action fails, confirm that both Telegram repository secrets are set and that you started a chat with your bot.

### 11. Test and monitor

The reminder and email checks run automatically. Use **Actions → Campus Copilot → Run workflow** only when you explicitly want a manual daily digest or to test a check. Inspect its logs in the Actions tab. Do not add commands that print environment variables or secret values.

Scheduled jobs use UTC:

- `*/15 * * * *` UTC = due personal reminders and Classroom email check (about every 15 minutes)
- `30 0-22/2 * * *` UTC = important assignment deadline milestone check every two hours (06:00, 08:00, ..., 04:00 Asia/Kolkata)

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
- SQLite stores job-ranking feedback in a GitHub Actions cache. Job digests are manual-only, so they do not create routine Telegram notifications.
