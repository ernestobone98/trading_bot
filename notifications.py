from pushbullet import Pushbullet
import os
from dotenv import load_dotenv

load_dotenv()

def send_pushbullet_alert(message):
    """Send notification using Pushbullet"""
    try:
        pb = Pushbullet(os.getenv('PUSHBULLET_API_KEY'))
        push = pb.push_note('Trading Bot Alert', message)
    except Exception as e:
        print(f"Error sending Pushbullet notification: {e}")
