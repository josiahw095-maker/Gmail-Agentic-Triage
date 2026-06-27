import os
import threading
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from concurrent.futures import ThreadPoolExecutor, as_completed

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = 'credentials.json'

_thread_local = threading.local()


def get_gmail_service():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def _thread_service():
    """Per-thread Gmail service for safe parallel reads."""
    if not hasattr(_thread_local, 'service'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        _thread_local.service = build('gmail', 'v1', credentials=creds)
    return _thread_local.service


def fetch_message_ids(service, max_emails=10000, since_hours=None):
    """Fast: just fetches message IDs via paginated list calls."""
    q = '-from:me'
    if since_hours:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        q += f' after:{int(cutoff.timestamp())}'

    ids = []
    page_token = None
    while True:
        response = service.users().messages().list(
            userId='me',
            q=q,
            labelIds=['INBOX', 'UNREAD'],
            maxResults=min(max_emails - len(ids), 500),
            pageToken=page_token
        ).execute()
        ids.extend([m['id'] for m in response.get('messages', [])])
        page_token = response.get('nextPageToken')
        if not page_token or len(ids) >= max_emails:
            break
    return ids[:max_emails]


def _fetch_one(msg_id):
    svc = _thread_service()
    full = svc.users().messages().get(userId='me', id=msg_id, format='full').execute()
    headers = {h['name']: h['value'] for h in full['payload']['headers']}
    return {
        'id': msg_id,
        'thread_id': full.get('threadId', msg_id),
        'subject': headers.get('Subject', '(no subject)'),
        'sender': headers.get('From', '(unknown sender)'),
        'body': extract_body(full['payload']),
        'date': headers.get('Date', '')
    }


def fetch_emails_for_batch(msg_ids, workers=10):
    """Fetch full content for a batch of IDs in parallel."""
    emails = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_one, mid): mid for mid in msg_ids}
        for future in as_completed(futures):
            try:
                emails.append(future.result())
            except Exception as e:
                print(f"[WARNING] Failed to fetch email {futures[future]}: {e}")
    return emails


def extract_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data', '')
                return _decode(data)
    return _decode(payload.get('body', {}).get('data', ''))


def _decode(data):
    import base64
    if not data:
        return ''
    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')


def mark_as_read(service, gmail_id):
    service.users().messages().modify(
        userId='me',
        id=gmail_id,
        body={'removeLabelIds': ['UNREAD']}
    ).execute()


_label_cache = {}


def apply_label(service, gmail_id, label_name):
    label_id = _cache_lookup(label_name) or get_or_create_label(service, label_name)
    service.users().messages().modify(
        userId='me',
        id=gmail_id,
        body={'addLabelIds': [label_id]}
    ).execute()


def _cache_lookup(label_name):
    if label_name in _label_cache:
        return _label_cache[label_name]
    lower = label_name.lower()
    for k, v in _label_cache.items():
        if k.lower() == lower:
            _label_cache[label_name] = v
            return v
    return None


def get_or_create_label(service, label_name):
    hit = _cache_lookup(label_name)
    if hit:
        return hit

    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        _label_cache[label['name']] = label['id']

    hit = _cache_lookup(label_name)
    if hit:
        return hit

    try:
        created = service.users().labels().create(
            userId='me',
            body={'name': label_name}
        ).execute()
        _label_cache[label_name] = created['id']
        return created['id']
    except Exception as e:
        if '409' in str(e):
            labels = service.users().labels().list(userId='me').execute().get('labels', [])
            for label in labels:
                _label_cache[label['name']] = label['id']
            hit = _cache_lookup(label_name)
            if hit:
                return hit
        raise


def prefetch_labels(service, category_names):
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        _label_cache[label['name']] = label['id']

    for name in category_names:
        if name not in _label_cache:
            created = service.users().labels().create(
                userId='me',
                body={'name': name}
            ).execute()
            _label_cache[name] = created['id']


def register_watch(service, project_id, topic_id):
    resp = service.users().watch(
        userId='me',
        body={
            'topicName': f'projects/{project_id}/topics/{topic_id}',
        }
    ).execute()
    return resp.get('historyId'), resp.get('expiration')


def get_new_message_ids(service, since_history_id):
    new_ids = []
    next_history_id = since_history_id
    page_token = None
    try:
        while True:
            resp = service.users().history().list(
                userId='me',
                startHistoryId=since_history_id,
                historyTypes=['messageAdded'],
                labelId='INBOX',
                pageToken=page_token
            ).execute()
            next_history_id = resp.get('historyId', next_history_id)
            for record in resp.get('history', []):
                for added in record.get('messagesAdded', []):
                    m = added['message']
                    labels = m.get('labelIds', [])
                    if 'INBOX' in labels and 'UNREAD' in labels:
                        new_ids.append(m['id'])
            page_token = resp.get('nextPageToken')
            if not page_token:
                break
        return new_ids, next_history_id
    except Exception as e:
        if '404' in str(e) or '400' in str(e):
            return None, since_history_id
        raise


def send_email(service, to, subject, body, html=False):
    import base64
    from email.mime.text import MIMEText
    message = MIMEText(body, 'html' if html else 'plain')
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId='me',
        body={'raw': raw}
    ).execute()
