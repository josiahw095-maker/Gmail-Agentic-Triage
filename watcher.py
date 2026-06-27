import os
import json
import time
import queue
from dotenv import load_dotenv
from google.cloud import pubsub_v1

from gmail_client import get_gmail_service, get_new_message_ids, fetch_message_ids, prefetch_labels
from triage import init_vertex, DEFAULT_CATEGORIES
from db import init_db, save_state, load_state
from main import process_email_ids, send_escalation_digest

load_dotenv()
PROJECT_ID = os.getenv('PROJECT_ID')
PUBSUB_SUBSCRIPTION = os.getenv('PUBSUB_SUBSCRIPTION')
MY_EMAIL = os.getenv('MY_EMAIL')

_work_queue = queue.Queue()


def handle_notification(message):
    """Runs in Pub/Sub background thread — only queue the historyId, no API calls."""
    try:
        data = json.loads(message.data.decode())
        history_id = str(data.get('historyId', ''))
        if history_id:
            _work_queue.put(history_id)
            print(f"[NOTIFICATION] historyId={history_id}")
    except Exception as e:
        print(f"[WARNING] Could not parse notification: {e}")
    message.ack()


def run_watcher():
    init_db()
    service = get_gmail_service()
    client = init_vertex()
    prefetch_labels(service, [f"triage/{c.split(':')[0]}" for c in DEFAULT_CATEGORIES])

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, PUBSUB_SUBSCRIPTION)
    streaming_pull = subscriber.subscribe(subscription_path, callback=handle_notification)
    print(f"Watching inbox via Pub/Sub ({subscription_path})...")

    try:
        while True:
            try:
                history_id = _work_queue.get(timeout=1)
            except queue.Empty:
                continue

            saved_id = load_state('history_id')
            new_ids, new_history_id = get_new_message_ids(service, saved_id or history_id)
            save_state('history_id', new_history_id)

            if new_ids is None:
                print("[WARNING] History ID expired — falling back to last hour")
                new_ids = fetch_message_ids(service, max_emails=50, since_hours=1)

            if new_ids and len(new_ids) > 50:
                print(f"[WARNING] {len(new_ids)} new emails in one burst — capping at 50 to limit API cost")
                new_ids = new_ids[:50]

            if new_ids:
                print(f"Triaging {len(new_ids)} new email(s)...")
                escalated = process_email_ids(service, client, new_ids, skip_from=[MY_EMAIL])
                if escalated:
                    send_escalation_digest(service, client, escalated)

    except KeyboardInterrupt:
        print("Stopping watcher...")
        streaming_pull.cancel()
        streaming_pull.result()


if __name__ == '__main__':
    while True:
        try:
            run_watcher()
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] Watcher crashed: {e} — restarting in 30s")
            time.sleep(30)
