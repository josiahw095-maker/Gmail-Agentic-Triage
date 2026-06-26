import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = 'credentials.json'

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


def fetch_unread_emails(service, max_emails=10):
    messages = []
    page_token = None

    while True:
        response = service.users().messages().list(
            userId='me',
            q='is:unread -from:me',
            maxResults=min(max_emails - len(messages), 500),
            pageToken=page_token
        ).execute()

        messages.extend(response.get('messages', []))
        page_token = response.get('nextPageToken')
        if not page_token or len(messages) >= max_emails:
            break

    messages = messages[:max_emails]

    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in full['payload']['headers']}
        subject = headers.get('Subject', '(no subject)')
        sender = headers.get('From', '(unknown sender)')
        body = extract_body(full['payload'])

        emails.append({
            'id': msg['id'],
            'subject': subject,
            'sender': sender,
            'body': body
        })

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


def apply_label(service, gmail_id, label_name):
    label_id = get_or_create_label(service, label_name)
    service.users().messages().modify(
        userId='me',
        id=gmail_id,
        body={'addLabelIds': [label_id]}
    ).execute()


def get_or_create_label(service, label_name):
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['name'] == label_name:
            return label['id']

    created = service.users().labels().create(
        userId='me',
        body={'name': label_name}
    ).execute()
    return created['id']


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
