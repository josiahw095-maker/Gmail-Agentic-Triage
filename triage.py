import os
from google import genai
from google.genai.types import HttpOptions
from dotenv import load_dotenv
from config import ESCALATE_IF_FROM, ESCALATE_IF_TOPIC, DEPRIORITIZE_IF_FROM
from db import load_corrections

load_dotenv()
PROJECT_ID = os.getenv('PROJECT_ID')
LOCATION = os.getenv('LOCATION')

DEFAULT_CATEGORIES = [
    'URGENT: Needs immediate attention',
    'ACTION: Requires a response or action but not urgent',
    'INFO: Informational only, no action needed',
    'ADS: Promotional emails, advertisements, marketing newsletters, deals, coupons, and any email whose primary purpose is to sell something or promote a brand — even if it contains useful information',
    'RECEIPT: Purchase confirmations and order receipts',
    'RECORDS: Official documents worth keeping on file, such as bank statements, tax forms, transcripts, insurance, and legal documents',
    'SPAM: Unwanted or irrelevant email',
    'OTHER: Does not fit any existing category'
]

CONFIDENCE_THRESHOLD = 80


def init_vertex():
    return genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        http_options=HttpOptions(api_version='v1')
    )


def classify_email(client, subject, body, categories=None):
    if categories is None:
        categories = DEFAULT_CATEGORIES

    category_list = '\n'.join(f'- {c}' for c in categories)

    interests_from = ', '.join(ESCALATE_IF_FROM) if ESCALATE_IF_FROM else 'none'
    interests_topic = ', '.join(ESCALATE_IF_TOPIC) if ESCALATE_IF_TOPIC else 'none'
    deprioritize_from = ', '.join(DEPRIORITIZE_IF_FROM) if DEPRIORITIZE_IF_FROM else 'none'

    corrections = load_corrections()
    corrections_text = ''
    if corrections:
        lines = ['The user has previously corrected these classifications:']
        for subj, original, corrected in corrections:
            lines.append(f'  - "{subj}": {original} → {corrected}')
        corrections_text = '\n'.join(lines) + '\n'

    prompt = f"""You are an email triage assistant for a college student. Classify the following email.

    Categories:
    {category_list}

    The user wants to be notified about emails from these senders even if they are ads: {interests_from}
    The user wants to be notified about emails on these topics even if they are ads: {interests_topic}
    If the email matches any of these, set ESCALATE to true.

    Emails from these senders should be classified as ADS and never escalated unless they contain an invoice, receipt, or important document: {deprioritize_from}

    {corrections_text}
    Email subject: {subject}
    Email body: {body}

    Respond in this exact format:
    CATEGORY: <category name only>
    CONFIDENCE: <0-100>
    ESCALATE: <true/false>
    REASON: <one sentence explanation>"""

    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    result = parse_response(response.text)

    if (result['confidence'] < CONFIDENCE_THRESHOLD or
            result['category'] in ('URGENT', 'ACTION') or
            result['category'] == 'OTHER'):
        result['escalate'] = True

    return result


def summarize_for_digest(client, subject, body, sender, reason):
    prompt = f"""You are summarizing an email that has been flagged for a college student's attention.
Provide a brief, scannable summary in this exact format:

CONTEXT: <one sentence explaining what this email is about>
ACTION: <one sentence on what the student should do, or "No action required" if informational>
BULLETS:
- <key detail>
- <key detail>
- <key detail if needed>

Email from: {sender}
Subject: {subject}
Reason flagged: {reason}
Body: {body[:1000]}"""

    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    return parse_summary(response.text)


def parse_summary(text):
    result = {'context': '', 'action': '', 'bullets': []}
    in_bullets = False
    for line in text.strip().split('\n'):
        if line.startswith('CONTEXT:'):
            result['context'] = line.split(':', 1)[1].strip()
        elif line.startswith('ACTION:'):
            result['action'] = line.split(':', 1)[1].strip()
        elif line.startswith('BULLETS:'):
            in_bullets = True
        elif in_bullets and line.strip().startswith('-'):
            result['bullets'].append(line.strip()[1:].strip())
    return result


def propose_new_categories(client, other_emails):
    if not other_emails:
        return []

    email_list = ''
    for i, (subject, body) in enumerate(other_emails, 1):
        email_list += f"\nEmail {i}:\nSubject: {subject}\nBody: {body[:500]}\n"

    prompt = f"""You are an email triage assistant. The following emails could not be classified into any existing category.
Analyze them as a group and propose the minimum number of new categories needed to cover all of them.
Some emails may share a category — do not create a separate category for each email.

Emails:
{email_list}

Respond with one entry per new category in this exact format, repeating for each category:
NAME: <short uppercase category name, one or two words>
DESCRIPTION: <one sentence describing what emails belong in this category>
COVERS: <comma-separated list of email numbers this category covers>
---"""

    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    return parse_proposed_categories(response.text)


def parse_response(text):
    result = {}
    for line in text.strip().split('\n'):
        if line.startswith('CATEGORY:'):
            result['category'] = line.split(':', 1)[1].strip()
        elif line.startswith('CONFIDENCE:'):
            result['confidence'] = int(line.split(':', 1)[1].strip())
        elif line.startswith('ESCALATE:'):
            result['escalate'] = line.split(':', 1)[1].strip().lower() == 'true'
        elif line.startswith('REASON:'):
            result['reason'] = line.split(':', 1)[1].strip()
    return result


def parse_proposed_categories(text):
    categories = []
    current = {}
    for line in text.strip().split('\n'):
        if line.strip() == '---':
            if 'name' in current and 'description' in current:
                categories.append(current)
            current = {}
        elif line.startswith('NAME:'):
            current['name'] = line.split(':', 1)[1].strip()
        elif line.startswith('DESCRIPTION:'):
            current['description'] = line.split(':', 1)[1].strip()
    if 'name' in current and 'description' in current:
        categories.append(current)
    return categories
