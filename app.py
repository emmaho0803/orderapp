from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                             FlexSendMessage, PostbackEvent)
import os
import re
from collections import Counter

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 記憶出席名單
attendees = []

# 預設的出席人名單
default_attendees = [
    "劉研", "趙副研", "阿錞", "智函", "詠彤", "子玄",
    "冠儒", "卓君", "悅婷", "欣儒", "芸樺", "育瑄"
]

# 發送出席人員 Flex 選單
def send_attendee_selection(reply_token):
    contents = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "請選擇今日出席者", "weight": "bold", "size": "md", "margin": "md"},
                {"type": "separator", "margin": "md"},
            ] + [
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": name,
                        "data": f"add:{name}"
                    },
                    "margin": "sm",
                    "style": "secondary",
                    "height": "sm"
                } for name in default_attendees
            ] + [
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": "➕ 自填姓名",
                        "data": "custom"
                    },
                    "margin": "md",
                    "style": "primary"
                },
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": "✅ 完成",
                        "data": "done"
                    },
                    "margin": "md",
                    "style": "primary"
                },
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": "🗑️ 清除",
                        "data": "clear"
                    },
                    "margin": "md",
                    "style": "danger"
                }
            ]
        }
    }

    line_bot_api.reply_message(
        reply_token,
        FlexSendMessage(alt_text="請選擇出席者", contents=contents)
    )

# 分析點餐內容並分類出席與非出席
def parse_order(text):
    lines = text.strip().split('\n')
    orders = []
    total_price_attendee = 0
    total_price_non_attendee = 0

    for line in lines:
        match = re.search(r'(.+?)：(.+?)\$?(\d+)', line)
        if match:
            name = match.group(1).strip()
            item = match.group(2).strip()
            price = int(match.group(3))
            is_attendee = name in attendees
            orders.append((name, item, price, is_attendee))

    counter = Counter()
    for name, item, price, is_attendee in orders:
        counter[item] += 1
        if is_attendee:
            total_price_attendee += price
        else:
            total_price_non_attendee += price

    result = "點餐統計結果：\n"
    for item, count in counter.items():
        result += f"{item}: {count}份\n"
    result += f"\n💰 出席者總金額：${total_price_attendee}"
    result += f"\n💰 非出席者總金額：${total_price_non_attendee}"

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

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data

    if data.startswith('add:'):
        name = data.split(':')[1]
        if name not in attendees:
            attendees.append(name)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"✅ 已加入出席者：{name}")
        )

    elif data == 'custom':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入自填出席者姓名（直接輸入名字）")
        )

    elif data == 'done':
        if attendees:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="出席者設定完成：\n" + ", ".join(attendees))
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ 尚未選擇任何出席者！")
            )

    elif data == 'clear':
        attendees.clear()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🗑️ 已清除出席者名單")

        )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text

    if user_text.strip() == "/設定出席者":
        send_attendee_selection(event.reply_token)
    elif any(kw in user_text for kw in ['：', '$']):
        summary = parse_order(user_text)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=summary)
        )
    elif len(user_text.strip()) <= 6:
        # 視為手動輸入出席者姓名
        name = user_text.strip()
        if name and name not in attendees:
            attendees.append(name)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✅ 已加入自填出席者：{name}")
            )

if __name__ == "__main__":
    app.run()
