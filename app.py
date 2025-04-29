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

# 狀態暫存
conversation_state = {}
order_cache = {}

# 分析點餐 + 出席名單，分類計算
def analyze_order(order_text, attendee_text):
    lines = order_text.strip().split('\n')
    attendees = re.split(r'[、\s]', attendee_text.strip())
    attendees = [a.strip() for a in attendees if a.strip()]
    
    orders = []
    total_attendee = 0
    total_non_attendee = 0
    counter = Counter()

    for line in lines:
        match = re.search(r'(.+?)：(.+?)\$?(\d+)', line)
        if match:
            name = match.group(1).strip()
            item = match.group(2).strip()
            price = int(match.group(3))
            counter[item] += 1
            if name in attendees:
                total_attendee += price
            else:
                total_non_attendee += price

    result = "點餐統計結果：\n"
    for item, count in counter.items():
        result += f"{item}: {count}份\n"
    result += f"\n💰 出席者總金額：${total_attendee}"
    result += f"\n💰 非出席者總金額：${total_non_attendee}"
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
    user_id = event.source.user_id
    msg = event.message.text.strip()

    # 狀態：輸入出席名單中
    if conversation_state.get(user_id) == "waiting_attendees":
        order_text = order_cache.get(user_id, "")
        result = analyze_order(order_text, msg)
        conversation_state[user_id] = None
        order_cache[user_id] = None
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
        return

    # 用戶傳點餐內容
    if "：" in msg and "$" in msg:
        order_cache[user_id] = msg
        conversation_state[user_id] = "waiting_meeting_confirm"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="今日是否有會議？")
        )
        return

    # 狀態：等待回覆是否有會議
    if conversation_state.get(user_id) == "waiting_meeting_confirm":
        if msg in ["是", "有","有的","沒錯","yes","有滴","恩"]:
            conversation_state[user_id] = "waiting_attendees"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入出席者姓名，用空格或頓號分隔（如：小明 阿華 小雲）")
            )
        else:
            # 沒有會議 → 全部算非出席者
            result = analyze_order(order_cache[user_id], "")
            conversation_state[user_id] = None
            order_cache[user_id] = None
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
