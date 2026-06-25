# Gmail Agentic Triage

WIP. This is an attempt to deal with the sea of ads that I as a college student deal with in my gmail. The end goal is to have this update my emails, and dynamically sort upon receiving mail. Funded by the GCP free trial for now. Emails flagged for escalation will eventually be escalated immediately, the model used is currently gemini 2.5 flash

## How it works

1. Fetches all unread emails from Gmail via the Gmail API
2. Classifies each email into a category using Gemini 2.5 Flash (Vertex AI)
3. Flags emails for escalation if they are urgent, require action, or if the model is uncertain
4. Saves new categories to the database if an email doesn't fit any existing category
5. Logs all results to a local SQLite database

## Categories

- **URGENT** — needs immediate attention (always escalated)
- **ACTION** — requires a response or action (always escalated)
- **INFO** — informational, no action needed
- **RECEIPT** — purchase confirmations and order receipts
- **RECORDS** — official documents worth keeping on file (bank statements, tax forms, transcripts, insurance, etc.)
- **ADS** — promotional emails and marketing
- **OTHER** — triggers a second model call to propose and save a new category

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
```
3. Run the app once to complete Gmail OAuth — it will open a browser and save `token.json` automatically
4. Authenticate Vertex AI:
```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
```

### Interest-based escalation

Edit `config.py` to flag ads from specific senders or on specific topics for escalation:

```python
ESCALATE_IF_FROM = ['steampowered.com', 'bestbuy.com']
ESCALATE_IF_TOPIC = ['GPU', 'internship', 'scholarship']
```

## Usage

```bash
python main.py
```

Results are printed to the terminal and logged to `triage.db`.
