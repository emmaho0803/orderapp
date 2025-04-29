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

# ✅ 新增：標準化客製化順序
def normalize_item(item):
    # 將全形括號換成半形
    item = item.replace("（", "(").replace("）", ")")

    match = re.match(r'(.+?)\((.+?)\)', item)
    if match:
        name = match.group(1).strip()
        custom = match.group(2)
        options = [opt.strip() for opt in re.split(r"[／/]", custom) if opt.strip()]
        sorted_custom = "/".join(sorted(options))
        return f"{name}（{sorted_custom}）"
    return item.strip()


def analyze_order(text):
    parts = re.split(r'[-—]{2,}', text.strip())
    counter = Counter()
    total_attendee = 0
    total_non_attendee = 0

    def parse_section(section_text, is_attendee=True):
        nonlocal total_attendee, total_non_attendee
        lines = section_text.strip().split("\n")
        for line in lines:
            match = re.search(r'：(.+?)\$?(\d+)', line)
            if match:
                raw_item = match.group(1).strip()
                item = normalize_item(raw_item)  # ✅ 呼叫標準化
                price = int(match.group(2))
                counter[item] += 1
                if is_attendee:
                    total_attendee += price
                else:
                    total_non_attendee += price

    if len(parts) > 1:
        parse_section(parts[0], is_attendee=True)
        parse_section(parts[1], is_attendee=False)
        result = "點餐統計結果：\n"
        for item, count in counter.items():
            result += f"{item}: {count}份\n"
        result += f"\n💰 出席者總金額：${total_attendee}"
        result += f"\n💰 非出席者總金額：${total_non_attendee}"
    else:
        parse_section(parts[0], is_attendee=True)
        result = "點餐統計結果：\n"
        for item, count in counter.items():
            result += f"{item}: {count}份\n"
        result += f"\n💰 總金額：${total_attendee}"

    return result

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    if "：" in msg and "$" in msg:
        result = analyze_order(msg)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請貼上完整點餐接龍內容（格式需包含『：』與金額『$』）。")
        )

if __name__ == "__main__":
    app.run()
