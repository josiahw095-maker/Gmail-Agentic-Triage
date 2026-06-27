# Gmail Agentic Triage

WIP. An agentic email triage system for Gmail, powered by Gemini 2.5 Flash on Vertex AI. Built to handle the volume of ads, newsletters, and noise that comes with being a college student. Categorizes new emails that come in via GCP APis using watcher.py, or can run batch jobs from main.py for large scale cleanup. Next goals are to allow for user creation of categories easily and consistent self-healing.

## How it works

1. Listens for new emails via Gmail push notifications (Pub/Sub) — or fetches in batch on startup
2. Classifies each email in parallel using Gemini 2.5 Flash (Vertex AI)
3. Applies a Gmail label (`triage/CATEGORY`) and marks each email as read
4. Flags emails for escalation if they are urgent, require action, or if the model is uncertain about a meaningful category
5. Sends an HTML digest email with AI-generated summaries, action items, and direct links to the original emails
6. Sends a phone push notification via ntfy when escalated emails are found
7. Logs all results to a local SQLite database

## Categories

| Label | Description | Escalates? |
|-------|-------------|------------|
| **URGENT** | Needs immediate attention | Always |
| **ACTION** | Requires a response or action | Always |
| **OTHER** | Doesn't fit any category | Always (if recent) |
| **INFO** | Informational, no action needed | Only if uncertain |
| **RECEIPT** | Purchase confirmations | No |
| **RECORDS** | Official documents — bank statements, tax forms, transcripts, etc. | No |
| **ADS** | Promotional emails and marketing | No |
| **SPAM** | Unwanted or irrelevant email | No |

Custom categories (e.g. `EDUCATION RECRUITMENT`) can be added to the database and will be available to the model on future runs. ADS, SPAM, RECEIPT, and RECORDS are "silent" — low confidence on these doesn't trigger escalation, since a wrong guess in these buckets is low cost.

---

## Quickstart

### 1. Prerequisites

- Python 3.x
- A Google Cloud project with Vertex AI and Cloud Pub/Sub APIs enabled
- Gmail API credentials (OAuth 2.0 Desktop App) — download as `credentials.json` from Google Cloud Console
- `gcloud` CLI installed and authenticated

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Create a `.env` file in the project root:

```
PROJECT_ID=your-gcp-project-id
LOCATION=us-central1
MY_EMAIL=your-gmail-address
NTFY_CHANNEL=your-ntfy-channel-name
PUBSUB_TOPIC=gmail-triage
PUBSUB_SUBSCRIPTION=gmail-triage-sub
```

### 4. Authenticate Gmail

Run once — a browser window will open and `token.json` is saved automatically:

```bash
python main.py --dry-run
```

### 5. Authenticate Vertex AI

```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
```

### 6. Set up phone notifications (optional but recommended)

1. Install the **ntfy** app on your phone (iOS or Android)
2. Subscribe to a channel with an unguessable name (e.g. `yourname-triage-abc123`)
3. Add that channel name as `NTFY_CHANNEL` in your `.env`

### 7. Configure sender rules

Copy `config.example.py` to `config.py` and fill in your preferences:

```python
# Always escalate these senders even if the email looks like an ad
ESCALATE_IF_FROM = ['steampowered.com', 'bestbuy.com']

# Always escalate emails containing these topics
ESCALATE_IF_TOPIC = ['GPU', 'internship', 'scholarship']

# Suppress these senders to ADS unless they contain an invoice or important document
DEPRIORITIZE_IF_FROM = ['linkedin.com', 'quora.com']
```

### 8. Set up real-time triage (Pub/Sub)

Create the Pub/Sub topic and subscription, and grant Gmail permission to publish:

```bash
gcloud pubsub topics create gmail-triage --project=YOUR_PROJECT_ID
gcloud pubsub subscriptions create gmail-triage-sub --topic=gmail-triage --ack-deadline=60 --project=YOUR_PROJECT_ID
gcloud pubsub topics add-iam-policy-binding gmail-triage \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=YOUR_PROJECT_ID
```

Then register the Gmail watch (re-run this weekly — it expires after 7 days):

```bash
python setup_watch.py
```

### 9. Run

> **Always do a dry run first.**

```bash
# Preview classifications — nothing in Gmail is touched
python main.py --dry-run

# Full run — labels applied, emails marked as read, digest sent if anything escalates
python main.py

# Efficient scheduled run — only fetch emails from the last N hours
python main.py --since-hours=1
```

---

## Real-time watcher

`watcher.py` listens continuously for new emails via Pub/Sub and triages them within seconds of arrival:

```bash
python watcher.py
```

For automatic startup, add two entries to Windows Task Scheduler:

| Task | Trigger | Command |
|------|---------|---------|
| Email watcher | On login | `python watcher.py` |
| Weekly catchup | Weekly | `python main.py --since-hours=168` |

Set both tasks to run at **Below Normal** priority so they yield to anything you're actively doing.

---

## Feedback and corrections

```bash
# Review escalated emails and correct any misclassifications
python feedback.py

# Review all recently triaged emails
python feedback.py --all
```

Press Enter to accept a classification, type a new category name to correct it, or `s` to skip. Corrections are logged and injected into the model prompt on future runs.

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | Batch triage orchestrator |
| `watcher.py` | Real-time Pub/Sub listener |
| `setup_watch.py` | One-time Gmail watch registration (re-run weekly) |
| `gmail_client.py` | Gmail API interactions |
| `triage.py` | Gemini classification and summarization |
| `db.py` | SQLite storage |
| `feedback.py` | CLI correction tool |
| `config.py` | Personal sender rules (gitignored) |
| `config.example.py` | Template for config.py |

## Safety

- `credentials.json`, `token.json`, `triage.db`, and `config.py` are all gitignored
- Use `--dry-run` to preview any run without touching Gmail
- The watcher ignores emails sent from your own address (triage digests don't get re-triaged)
- Already-processed emails are skipped on restart, so crashes are safe to recover from
- Email bodies are truncated to 3,000 characters before being sent to Gemini — long bodies can't inflate API costs
- The classification prompt explicitly instructs the model to ignore any instructions embedded in email content (prompt injection defense)
- The real-time watcher caps classification at 50 emails per Pub/Sub notification burst — a flood of incoming emails won't trigger unbounded Vertex AI spend; the weekly scheduled run catches any backlog
- Gmail's own spam filter handles the bulk of junk before it reaches the triage pipeline — emails in Spam are never in INBOX and are never fetched
