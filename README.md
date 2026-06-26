# Gmail Agentic Triage

WIP. This is an attempt to deal with the sea of ads that I as a college student deal with in my gmail. Funded by the GCP free trial, the model used is currently gemini 2.5 flash. This will eventually be a scheduled service, and in the future I plan to use the database this build for analysis.

<!-- TODO: update this intro once scheduling is implemented and the initial inbox clean is done -->

## How it works

1. Fetches all unread emails from Gmail via the Gmail API
2. Classifies each email in parallel using Gemini 2.5 Flash (Vertex AI)
3. Applies a Gmail label (`triage/CATEGORY`) and marks each email as read
4. Flags emails for escalation if they are urgent, require action, or if the model is uncertain
5. Sends an HTML digest email with AI-generated summaries, action items, and links to the original emails
6. Sends a phone push notification via ntfy when escalated emails are found
7. After every 100 emails, runs a batch analysis of any unclassified emails and proposes new categories — saved to the database and used in future runs
8. Logs all results to a local SQLite database

## Quickstart

### 1. Prerequisites
- Python 3.x
- A Google Cloud project with the Vertex AI API enabled
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
```

### 4. Authenticate Gmail

Run once to complete OAuth — a browser window will open and `token.json` will be saved automatically:

```bash
python main.py --dry-run
```

### 5. Authenticate Vertex AI

```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
```

### 6. Set up phone notifications (optional)

1. Install the **ntfy** app on your phone (iOS or Android — search "ntfy")
2. Subscribe to a channel with an unguessable name (e.g. `yourname-triage-abc123`)
3. Add that channel name as `NTFY_CHANNEL` in your `.env`

Test it before running a full triage:

```bash
python test_notify.py
```

### 7. Configure sender rules

Copy `config.example.py` to `config.py` and fill in your preferences:

```python
# Always escalate these senders even if the email looks like an ad
ESCALATE_IF_FROM = ['steampowered.com', 'bestbuy.com']

# Always escalate emails containing these topics even if they look like ads
ESCALATE_IF_TOPIC = ['GPU', 'internship', 'scholarship']

# Suppress these senders to ADS unless they contain an invoice or important document
DEPRIORITIZE_IF_FROM = ['linkedin.com', 'quora.com']
```

### 8. Run

> **Always do a dry run first.**

```bash
# Preview classifications — nothing in Gmail is touched
python main.py --dry-run

# Full run — labels applied, emails marked as read, digest and notification sent
python main.py
```

---

## Categories

- **URGENT** — needs immediate attention (always escalated)
- **ACTION** — requires a response or action (always escalated)
- **INFO** — informational, no action needed
- **RECEIPT** — purchase confirmations and order receipts
- **RECORDS** — official documents worth keeping on file (bank statements, tax forms, transcripts, insurance, etc.)
- **ADS** — promotional emails and marketing
- **OTHER** — collected across the run and analyzed as a batch to propose new categories

## Self-healing categories

When emails don't fit any existing category, they are held until the end of each 100-email batch. The model then analyzes them as a group and proposes the minimum number of new categories needed to cover them all — grouping similar emails rather than creating a separate category for each. New categories are saved to `triage.db` and applied to all future runs automatically.

## Feedback and corrections

```bash
# Review escalated emails and correct any misclassifications
python feedback.py

# Review all recently triaged emails (not just escalated)
python feedback.py --all
```

Press Enter to confirm a category, type a new category name to reclassify, or `s` to skip. Corrections are logged and injected into the classification prompt on future runs so the model learns from them.
