import sys
from db import init_db, load_escalated_emails, load_recent_emails, log_correction
from triage import DEFAULT_CATEGORIES

ALL_CATEGORIES = [c.split(':')[0] for c in DEFAULT_CATEGORIES if c.split(':')[0] != 'OTHER']


def run_feedback(show_all=False):
    init_db()
    emails = load_recent_emails() if show_all else load_escalated_emails()

    if not emails:
        label = "triaged" if show_all else "escalated"
        print(f"No {label} emails to review.")
        return

    label = "recently triaged" if show_all else "escalated"
    print(f"{len(emails)} {label} email(s) to review.")
    print("Press Enter to confirm, type a category to reclassify, or 's' to skip.\n")

    for gmail_id, subject, sender, category in emails:
        print(f"Subject:  {subject}")
        print(f"From:     {sender}")
        print(f"Category: {category}")
        print(f"Options:  {', '.join(ALL_CATEGORIES)}")

        response = input("Action [Enter=confirm, s=skip, or category]: ").strip().upper()

        if response == 'S':
            print("Skipped.\n")
        elif response and response != category:
            log_correction(gmail_id, subject, category, response)
            print(f"Logged: {category} → {response}\n")
        else:
            print("Confirmed.\n")


if __name__ == '__main__':
    show_all = '--all' in sys.argv
    run_feedback(show_all=show_all)
