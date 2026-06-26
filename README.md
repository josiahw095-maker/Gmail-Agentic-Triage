# Gmail Agentic Triage

WIP. This is an attempt to deal with the sea of ads that I as a college student deal with in my gmail. Funded by the GCP free trial, the model used is currently gemini 2.5 flash. This will eventually be a scheduled service, and in the future I plan to use the database this build for analysis.

## How it works

1. Fetches all unread emails from Gmail via the Gmail API
2. Classifies each email into a category using Gemini 2.5 Flash (Vertex AI)
3. Applies a Gmail label (`triage/CATEGORY`) and marks each email as read
4. Flags emails for escalation if they are urgent, require action, or if the model is uncertain
5. Sends an escalation digest email listing everything that needs attention
6. After every 100 emails, runs a batch analysis of any unclassified emails and proposes new categories — these are saved to the database and used in future runs
7. Logs all results to a local SQLite database

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

After a triage run, you can review flagged emails and correct any misclassifications:

```bash
# Review only escalated emails
python feedback.py

# Review all recently triaged emails
python feedback.py --all
```

Press Enter to confirm a category, type a new category name to reclassify, or `s` to skip. Corrections are logged and injected into the classification prompt on future runs so the model learns from them.

## Setup

### Prerequisites
- Python 3.x
- A Google Cloud project with the Vertex AI API enabled
- Gmail API credentials (OAuth 2.0, Desktop App)
- `gcloud` CLI installed and authenticated

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

1. Download `credentials.json` from Google Cloud Console and place it in the project root
2. Create a `.env` file:
```
PROJECT_ID=your-gcp-project-id
LOCATION=us-central1
MY_EMAIL=your-gmail-address
```
3. Run the app once to complete Gmail OAuth — it will open a browser and save `token.json` automatically
4. Authenticate Vertex AI:
```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
```

### Interest-based escalation

Edit `config.py` to tune how the system treats emails from specific senders:

```python
# Always escalate these senders even if the email looks like an ad
ESCALATE_IF_FROM = ['steampowered.com', 'bestbuy.com']

# Always escalate emails containing these topics even if they look like ads
ESCALATE_IF_TOPIC = ['GPU', 'internship', 'scholarship']

# Suppress these senders to ADS unless they contain an invoice or important document
DEPRIORITIZE_IF_FROM = ['linkedin.com', 'quora.com']
```

## Usage

> **New to the project or want to test safely? Start with `--dry-run`.**

```bash
# Preview classifications without touching your inbox
# No labels applied, nothing marked as read, no digest sent
python main.py --dry-run

# Full run — applies labels, marks as read, sends escalation digest
python main.py

# Limit to N emails (useful for testing)
# Edit max_emails in main.py or change the default
python main.py  # default is 10 during development
```

### Reviewing classifications

```bash
# Review escalated emails and correct any misclassifications
python feedback.py

# Review all recently triaged emails (not just escalated)
python feedback.py --all
```

Press Enter to confirm a category, type a new category name to reclassify, or `s` to skip. Corrections are logged and injected into the classification prompt on future runs so the model learns from them.

Results are printed to the terminal, Gmail labels are applied, and everything is logged to `triage.db`.
