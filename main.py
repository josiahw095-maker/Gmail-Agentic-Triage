from gmail_client import get_gmail_service, fetch_unread_emails
from triage import init_vertex, classify_email
from db import init_db, log_email, save_category, load_categories


def run_triage(max_emails=10):
    init_db()
    service = get_gmail_service()
    client = init_vertex()

    saved_categories = load_categories()
    emails = fetch_unread_emails(service, max_emails=max_emails)

    for email in emails:
        result = classify_email(
            client,
            email['subject'],
            email['body'],
            categories=saved_categories if saved_categories else None
        )

        if 'new_category' in result:
            save_category(result['new_category']['name'], result['new_category']['description'])

        log_email(
            gmail_id=email['id'],
            subject=email['subject'],
            sender=email['sender'],
            category=result['category'],
            confidence=result['confidence'],
            escalated=result['escalate'],
            reason=result['reason']
        )

        print(f"[{result['category']}] {email['subject']}")
        print(f"  Sender: {email['sender']}")
        print(f"  Confidence: {result['confidence']}%")
        print(f"  Escalate: {result['escalate']}")
        print(f"  Reason: {result['reason']}")
        if 'new_category' in result:
            print(f"  New category created: {result['new_category']['name']}")
        print()


if __name__ == '__main__':
    run_triage(max_emails=10)
