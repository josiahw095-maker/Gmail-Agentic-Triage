import os
from dotenv import load_dotenv
from gmail_client import get_gmail_service, register_watch
from db import init_db, save_state

load_dotenv()
PROJECT_ID = os.getenv('PROJECT_ID')
PUBSUB_TOPIC = os.getenv('PUBSUB_TOPIC')

if __name__ == '__main__':
    init_db()
    service = get_gmail_service()
    history_id, expiration = register_watch(service, PROJECT_ID, PUBSUB_TOPIC)
    save_state('history_id', history_id)

    from datetime import datetime
    exp_ms = int(expiration)
    exp_date = datetime.fromtimestamp(exp_ms / 1000).strftime('%Y-%m-%d %H:%M')
    print(f"Watch registered. History ID: {history_id}")
    print(f"Expires: {exp_date} (renew before then — add to weekly job)")
