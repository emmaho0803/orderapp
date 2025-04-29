from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import re
from collections import Counter

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

def parse_order(text):
    lines = text.strip().split('\n')
    items = []
    for line in lines:
        match = re.search(r'：(.+?)\$?\d+', line)
        if match:
            item = match.group(1).strip()
            items.append(item)
    counter = Counter(items)
    result = ""
    for item, count in counter.items():
        result += f"{item}: {count}份\n"
    return result

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    if "：" in user_text and "$" in user_text:
        summary = parse_order(user_text)
        reply = f"點餐統計結果：\n{summary}"
    else:
        reply = "請貼上接龍訊息（格式需包含「：」、「$」）！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run()
