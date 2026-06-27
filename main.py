import os
import sys
import time
import random
import requests
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from gmail_client import get_gmail_service, fetch_message_ids, fetch_emails_for_batch, mark_as_read, apply_label, send_email, prefetch_labels
from triage import init_vertex, classify_email, summarize_for_digest, DEFAULT_CATEGORIES
from db import init_db, log_email, load_categories, filter_unprocessed

load_dotenv()
MY_EMAIL = os.getenv('MY_EMAIL')
NTFY_CHANNEL = os.getenv('NTFY_CHANNEL')

BATCH_SIZE = 100
MAX_WORKERS = 5
ESCALATE_CUTOFF_DAYS = 30
MAX_RETRIES = 4


def is_recent(date_str):
    if not date_str:
        return True
    try:
        email_date = parsedate_to_datetime(date_str)
        cutoff = datetime.now(timezone.utc) - timedelta(days=ESCALATE_CUTOFF_DAYS)
        return email_date >= cutoff
    except Exception:
        return True


def classify_only(email, client, saved_categories):
    for attempt in range(MAX_RETRIES):
        try:
            result = classify_email(
                client,
                email['subject'],
                email['body'],
                categories=saved_categories if saved_categories else None
            )
            return email, result
        except Exception as e:
            if '429' in str(e) and attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt + random.uniform(0, 1)
                time.sleep(wait)
            else:
                raise


def process_email_ids(service, client, message_ids, dry_run=False, skip_from=None):
    """Classify and label a list of email IDs. Returns list of escalated (email, result) pairs."""
    escalated = []

    for batch_start in range(0, len(message_ids), BATCH_SIZE):
        batch_ids = filter_unprocessed(message_ids[batch_start:batch_start + BATCH_SIZE])
        if not batch_ids:
            continue
        batch_num = batch_start // BATCH_SIZE + 1
        print(f"--- Batch {batch_num}: fetching {len(batch_ids)} emails ---")
        batch = fetch_emails_for_batch(batch_ids)
        if skip_from:
            batch = [e for e in batch if not any(addr in e.get('sender', '') for addr in skip_from)]
        saved_categories = load_categories()
        results = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(classify_only, email, client, saved_categories): email
                for email in batch
            }
            for future in as_completed(futures):
                try:
                    email, result = future.result()
                    results.append((email, result))
                except Exception as e:
                    email = futures[future]
                    print(f"[ERROR] Failed to classify '{email['subject']}': {e}")

        for email, result in results:
            if not dry_run:
                log_email(
                    gmail_id=email['id'],
                    subject=email['subject'],
                    sender=email['sender'],
                    category=result.get('category', 'UNKNOWN'),
                    confidence=result.get('confidence', 0),
                    escalated=result.get('escalate', False),
                    reason=result.get('reason', '')
                )
                apply_label(service, email['id'], f"triage/{result.get('category', 'UNKNOWN')}")
                mark_as_read(service, email['id'])

            if result.get('escalate') and is_recent(email.get('date', '')):
                escalated.append((email, result))

            print(f"[{result.get('category', 'UNKNOWN')}] {email['subject']}")
            print(f"  Sender: {email['sender']}")
            print(f"  Confidence: {result.get('confidence', '?')}%")
            print(f"  Escalate: {result.get('escalate', '?')}")
            print(f"  Reason: {result.get('reason', '?')}")
            print()

    return escalated


def run_triage(max_emails=10000, dry_run=False, since_hours=None):
    init_db()
    service = get_gmail_service()
    client = init_vertex()

    if dry_run:
        print('--- DRY RUN: no labels will be applied and no emails marked as read ---\n')

    prefetch_labels(service, [f"triage/{c.split(':')[0]}" for c in DEFAULT_CATEGORIES])

    message_ids = fetch_message_ids(service, max_emails=max_emails, since_hours=since_hours)
    print(f"Found {len(message_ids)} unread email(s) in inbox.\n")

    escalated = process_email_ids(service, client, message_ids, dry_run)

    if escalated and not dry_run:
        send_escalation_digest(service, client, escalated)
    elif escalated and dry_run:
        print(f"--- DRY RUN: {len(escalated)} email(s) would have been escalated ---")


def send_escalation_digest(service, client, escalated):
    blocks = []
    for email, result in escalated:
        summary = summarize_for_digest(client, email['subject'], email['body'], email['sender'], result['reason'])
        gmail_link = f"https://mail.google.com/mail/u/{MY_EMAIL}/#all/{email.get('thread_id', email['id'])}"
        bullets_html = ''.join(f"<li style='margin:4px 0'>{b}</li>" for b in summary['bullets'])
        blocks.append(f"""
        <div style='border:1px solid #ddd;border-radius:6px;padding:16px;margin-bottom:20px;font-family:sans-serif'>
            <p style='margin:0 0 4px 0;font-size:11px;color:#888;text-transform:uppercase'>{result['category']}</p>
            <h2 style='margin:0 0 4px 0;font-size:16px'>{email['subject']}</h2>
            <p style='margin:0 0 12px 0;color:#555;font-size:13px'>From: {email['sender']}</p>
            <p style='margin:0 0 6px 0'><strong>Context:</strong> {summary['context']}</p>
            <p style='margin:0 0 6px 0'><strong>Action:</strong> {summary['action']}</p>
            <ul style='margin:6px 0 12px 0;padding-left:20px'>{bullets_html}</ul>
            <a href='{gmail_link}' style='color:#1a73e8;font-size:13px'>Open in Gmail →</a>
        </div>""")

    body = f"""
    <div style='max-width:600px;margin:0 auto;padding:20px;font-family:sans-serif'>
        <h1 style='font-size:20px;margin-bottom:4px'>Triage Digest</h1>
        <p style='color:#555;margin-top:0'>{len(escalated)} email(s) flagged for your attention</p>
        {''.join(blocks)}
    </div>"""

    send_email(service, MY_EMAIL, f'[TRIAGE] {len(escalated)} email(s) need your attention', body, html=True)
    send_phone_notification(len(escalated))
    print(f"Escalation digest sent — {len(escalated)} email(s) flagged.")


def send_phone_notification(count):
    if not NTFY_CHANNEL:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_CHANNEL}",
            headers={
                'Title': 'Email Triage',
                'Priority': 'high',
                'Tags': 'email'
            },
            data=f"{count} email(s) need your attention. Check your digest."
        )
    except Exception as e:
        print(f"[WARNING] Phone notification failed: {e}")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    since_hours = None
    for arg in sys.argv:
        if arg.startswith('--since-hours='):
            since_hours = int(arg.split('=')[1])
    run_triage(max_emails=10000, dry_run=dry_run, since_hours=since_hours)
