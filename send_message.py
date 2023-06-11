import subprocess
import sys
from main import get_valid_phone_number,format_phone_number

def send_message(recipient, message):
    '''
    Sends a message to a recipient
    '''
    subprocess.run(['osascript', '-e', 'on run {targetBuddyPhone, targetMessage}', '-e', 'tell application "Messages"', '-e', 'set targetService to 1st service whose service type = iMessage', '-e', 'set targetBuddy to buddy targetBuddyPhone of targetService', '-e', 'send targetMessage as text to targetBuddy', '-e', 'end tell', '-e', 'end run', recipient, *message])

if __name__ == "__main__":
    try:
        args = sys.argv
        print(args)
        recipient = args[1]
        message = args[2]
        phone_number = get_valid_phone_number(recipient)
        if phone_number is None:
            print("Invalid phone number",phone_number)
        else:
            print("Phone Number:", phone_number)
            print("Message:", message)
            # send_message(phone_number, [message])
    except Exception as e:
        print("Error:", e)
