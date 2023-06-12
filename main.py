from imessage_reader import data_container
from dotenv import dotenv_values
import sqlite3
import openai
import os
import subprocess
import datetime
import time
import sys
import re


#INDEXES
DATE_INDEX= 2
RECIP_INDEX = 0
MESSAGE_INDEX = 1
WHO_SENT = 5

#KEYS
env_vars = dotenv_values()
api_key = env_vars["OPENAI_API_KEY"]

#OPENAI
openai.api_key = api_key
completion = openai.ChatCompletion()

#GLOBAL VARIABLES
init_chat_log = [{"role": "system", "content": 
                  "You are me. You are responding a series of imessages, you will respond back in the same language as the messages sent by me. Respond to the text based on the previous messages as if you were me. "
                  "Rules Include:"
                  "Only include the message to be sent back nothing else. For example do not start with 'me: ' or 'recipient: '"
                  "If you want to send a message that is not a response to the previous message, respond with the context of the previous message sent by me. "
                  "If the previous message begins 'me:' then it was sent by me. If the previous message begins with 'recipient:' then it was sent by the person i am texting. "
                  "ONLY INCLUDE ONE MESSAGE TO BE SENT NOTHING MORE. NOT 'Me: ' or 'Recipient: '"
                  },]
SQL_CMD = (
    "SELECT "
    "text, "
    "datetime((date / 1000000000) + 978307200, 'unixepoch', 'localtime'),"
    "handle.id, "
    "handle.service, "
    "message.destination_caller_id, "
    "message.is_from_me, "
    "message.attributedBody, "
    "message.cache_has_attachments "
    "FROM message "
    "JOIN handle on message.handle_id=handle.ROWID"
)
u = os.popen('id -un').read().replace("\n", "")
DB_PATH = "/Users/" + u + "/Library/Messages/chat.db"


def fetch_db_data(db, command) -> list:
    """
    Send queries to the sqlite database and return the results.
    :param db: The path to the database.
    :param command: The Sqlite command.
    :return: Data from the database
    """
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(command)
        return cur.fetchall()
    except Exception as e:
        sys.exit("Error reading the database: %s" % e)

def _read_database() -> list:
    """
    Fetch data from the database and store the data in a list.
    :return: List containing the user id, messages, the service and the account
    """

    rval = fetch_db_data(DB_PATH, SQL_CMD)

    data = []
    for row in rval:
        text = row[0]
        if row[7] == 1:
            text = "<Message with no text, but an attachment.>"
        # the chatdb has some weird behavior where sometimes the text value is None
        # and the text string is buried in an binary blob under the attributedBody field.
        if text is None and row[6] is not None:
            try:
                text = row[6].split(b'NSString')[1]
                text = text[5:]  # stripping some preamble which generally looks like this: b'\x01\x94\x84\x01+'

                if text[0] == 129:  # this 129 is b'\x81, python indexes byte strings as ints, this is equivalent to text[0:1] == b'\x81'
                    length = int.from_bytes(text[1:3], 'little')
                    text = text[3:length + 3]
                else:
                    length = text[0]
                    text = text[1:length + 1]
                text = text.decode()
            except Exception as e:
                print("ERROR: Can't read a message.")
                print(e)

        data.append(
            data_container.MessageData(
                row[2], text, row[1], row[3], row[4], row[5]
            )
        )

    return data

def get_messages() -> list:
        """
        Create a list with tuples (user id, message, date, service, account, is_from_me)
        This method is for module usage.
        :return: List with tuples (user id, message, date, service, account, is_from_me)
        """
        fetched_data = _read_database()
        users = []
        messages = []
        dates = []
        service = []
        account = []
        is_from_me = []

        for data in fetched_data:
            users.append(data.user_id)
            messages.append(data.text)
            dates.append(data.date)
            service.append(data.service)
            account.append(data.account)
            is_from_me.append(data.is_from_me)

        data = list(zip(users, messages, dates, service, account, is_from_me))

        return data

def get_history(recipient):
    '''
    Gets the message history of a recipient
    :recipient: The recipient of the message history
    :return: A dictionary of the message history
    '''
    try:
        messages = get_messages()
        who_sent = {}
        message_history = {}
        for message in messages:
            if message[RECIP_INDEX] == recipient:
                if message[WHO_SENT] == 0:
                    message_history[message[DATE_INDEX]] = {"from": "Recipent", "message": message[MESSAGE_INDEX]}
                else:
                    message_history[message[DATE_INDEX]] = {"from": "Me", "message": message[MESSAGE_INDEX]}
        return message_history
    except Exception as e:
        print("Error:", e)
        return


def get_prompt(message_history):
    '''
    Formats text messages to send to the model
    :message_history: The message history of the recipient
    :return: A string prompt to send to the model
    '''
    last_5_dates = list(message_history.keys())[-10:]
    last_5_messages = []
    for date in last_5_dates:
        sender = message_history[date]['from']
        message = message_history[date]['message']
        last_5_messages.append(f"{sender}: {message}")
    prompt = " ".join(last_5_messages)
    return prompt

def generate_message(prompt,chat_log=None):
    '''
    Generates a message based on the prompt
    :prompt: The list of messages to be passed
    :chat_log: Chat log if valid
    '''
    if chat_log is None:
        chat_log = init_chat_log
    chat_log = chat_log + [{'role': 'user', 'content': prompt}]
    response = completion.create(model='gpt-3.5-turbo', messages=chat_log)
    answer = response.choices[0]['message']['content']
    chat_log = chat_log + [{'role': 'assistant', 'content': answer}]
    return answer, chat_log


def send_message(recipient, message):
    '''
    Sends a message to a recipient
    :recipient: The recipient of the message
    :message: The message to send
    :return: None
    '''
    subprocess.run(['osascript', '-e', 'on run {targetBuddyPhone, targetMessage}', '-e', 'tell application "Messages"', '-e', 'set targetService to 1st service whose service type = iMessage', '-e', 'set targetBuddy to buddy targetBuddyPhone of targetService', '-e', 'send targetMessage as text to targetBuddy', '-e', 'end tell', '-e', 'end run', recipient, *message])

def format_phone_number(phone_number):
    '''
    Formats a phone number to the format +1xxxxxxxxxx
    :phone_number: The phone number to format
    :return: The formatted phone number
    '''
    digits = ''.join(filter(str.isdigit, phone_number))
    if len(digits) == 10:
        digits = '1' + digits
    formatted_number = '+{}{}{}{}'.format(digits[:2], digits[2:5], digits[5:8], digits[8:])
    
    return formatted_number[0:12]

def get_valid_phone_number(phone_number):
    '''
    Checks if a phone number is valid
    :phone_number: The phone number to check
    :return: The formatted phone number if valid, None otherwise
    '''
    formatted_number = format_phone_number(phone_number)
    if len(formatted_number) == 12:
        return formatted_number
    return None 

def main(recipient):
    '''
    Main function that runs prompt gen and response 
    :recipient: The phone number to chat with
    '''
    message_history = get_history(recipient)
    prompt = get_prompt(message_history)
    # print("Prompt:", prompt)
    response, chat_log = generate_message(prompt)
    if response.startswith("Me: "):
        response = response[4:]
    print(response)

if __name__ == "__main__":
    recipient = sys.argv[1]
    phone_number = get_valid_phone_number(recipient)
    if phone_number is None:
        print("Invalid phone number",recipient)
    else:
        main(phone_number)
