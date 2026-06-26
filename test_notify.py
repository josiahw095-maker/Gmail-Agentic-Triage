from dotenv import load_dotenv
import os
import requests

load_dotenv()
channel = os.getenv('NTFY_CHANNEL')

requests.post(
    f"https://ntfy.sh/{channel}",
    headers={'Title': 'Email Triage', 'Priority': 'high', 'Tags': 'email'},
    data='Test notification — ntfy is working!'
)
print(f"Notification sent to channel: {channel}")
