import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from gmail_client import get_gmail_service, fetch_unread_emails, mark_as_read, apply_label, send_email
from triage import init_vertex, classify_email, propose_new_categories
from db import init_db, log_email, save_category, load_categories

load_dotenv()
MY_EMAIL = os.getenv('MY_EMAIL')

BATCH_SIZE = 100
MAX_WORKERS = 10


def classify_only(email, client, saved_categories):
    result = classify_email(
        client,
        email['subject'],
        email['body'],
        categories=saved_categories if saved_categories else None
    )
    return email, result


def run_triage(max_emails=100, dry_run=False):
    init_db()
    service = get_gmail_service()
    client = init_vertex()

    if dry_run:
        print('--- DRY RUN: no labels will be applied and no emails marked as read ---\n')

    emails = fetch_unread_emails(service, max_emails=max_emails)
    print(f"Fetched {len(emails)} unread email(s).\n")
    escalated = []

    for batch_start in range(0, len(emails), BATCH_SIZE):
        batch = emails[batch_start:batch_start + BATCH_SIZE]
        saved_categories = load_categories()
        other_emails = []
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
            if result.get('category') == 'OTHER':
                other_emails.append((email['subject'], email['body']))

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

            if result.get('escalate'):
                escalated.append((email, result))

            print(f"[{result.get('category', 'UNKNOWN')}] {email['subject']}")
            print(f"  Sender: {email['sender']}")
            print(f"  Confidence: {result.get('confidence', '?')}%")
            print(f"  Escalate: {result.get('escalate', '?')}")
            print(f"  Reason: {result.get('reason', '?')}")
            print()

        if other_emails and not dry_run:
            print(f"Running category proposal for {len(other_emails)} unclassified email(s)...")
            new_categories = propose_new_categories(client, other_emails)
            for cat in new_categories:
                save_category(cat['name'], cat['description'])
                print(f"New category saved: {cat['name']} — {cat['description']}")

    if escalated and not dry_run:
        send_escalation_digest(service, escalated)
    elif escalated and dry_run:
        print(f"--- DRY RUN: {len(escalated)} email(s) would have been escalated ---")


def send_escalation_digest(service, escalated):
    lines = ['The following emails were flagged for your attention:\n']
    for email, result in escalated:
        lines.append(f"[{result['category']}] {email['subject']}")
        lines.append(f"From:   {email['sender']}")
        lines.append(f"Reason: {result['reason']}")
        lines.append('')
        snippet = email['body'].strip()[:500].replace('\n', ' ')
        lines.append(snippet)
        lines.append('')
        lines.append('-' * 60)
        lines.append('')

    send_email(service, MY_EMAIL, '[TRIAGE] Emails needing your attention', '\n'.join(lines))
    print(f"Escalation digest sent — {len(escalated)} email(s) flagged.")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    run_triage(max_emails=100, dry_run=dry_run)
