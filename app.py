from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction, ImageSendMessage
import os
import re
import random
from collections import Counter
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from functools import lru_cache

app = Flask(__name__)

# 環境變數設定
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
SPREADSHEET_KEY = os.getenv('GOOGLE_SHEET_KEY')

# Line Bot 初始化
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# Google API 設定
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]
CREDENTIALS_PATH = '/etc/secrets/credentials.json'
SHEET_NAME = '餐廳資料'

# 初始化 Google 服務
def init_google_service(service_name='sheets', version='v4'):
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH, 
            scopes=SCOPES
        )
        
        if service_name == 'sheets':
            return gspread.authorize(creds)
        elif service_name == 'drive':
            return build('drive', 'v3', credentials=creds)
            
    except Exception as e:
        print(f"Google {service_name} 初始化失敗: {str(e)}")
        return None

# Google Drive 圖片處理
@lru_cache(maxsize=100)
def get_image_url(file_id):
    """處理各種圖片 URL 格式"""
    if not file_id or str(file_id).lower() in ('none', 'null', ''):
        return None
        
    # 如果已經是完整 URL
    if str(file_id).startswith(('http://', 'https://')):
        return file_id
        
    # 處理 Google Drive 檔案 ID
    return f"https://drive.google.com/uc?export=view&id={file_id}"

# 餐廳資料處理
def load_restaurants_data():
    try:
        gc = init_google_service('sheets')
        if not gc:
            raise Exception("無法連接 Google Sheets")
        
        sheet = gc.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
        records = sheet.get_all_records()
        
        restaurants = []
        for row in records:
            restaurants.append({
                '餐廳名稱': row.get('餐廳名稱', ''),
                '電話': row.get('電話', ''),
                '推薦星星': float(row.get('推薦星星', 0)),
                '價位區間': row.get('價位區間', ''),
                '營業時間': row.get('營業時間', '未知'),
                '地址': row.get('地址', '未知'),
                '圖片url': get_image_url(row.get('圖片url', ''))
            })
        return restaurants
        
    except Exception as e:
        print(f"載入餐廳資料失敗: {str(e)}")
        return []

# 全局餐廳資料
RESTAURANTS_DATA = load_restaurants_data()

def normalize_item(item):
    # 將全形括號與分隔符轉換為半形
    item = item.replace("（", "(").replace("）", ")").replace("／", "/")

    match = re.match(r'(.+?)\((.+?)\)', item)
    if match:
        name = match.group(1).strip()
        options = [opt.strip() for opt in match.group(2).split("/") if opt.strip()]
        sorted_custom = "/".join(sorted(options))
        return f"{name}（{sorted_custom}）"
    return item.strip()

# 指令處理函數
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
                item = normalize_item(raw_item)
                price = int(match.group(2))
                counter[item] += 1
                if is_attendee:
                    total_attendee += price
                else:
                    total_non_attendee += price

    if len(parts) > 1:
        parse_section(parts[0], True)
        parse_section(parts[1], False)
        result = "🍽️ 點餐統計結果：\n" + "\n".join(f"{item}: {count}份" for item, count in counter.items())
        result += f"\n\n💰 出席者總金額：${total_attendee}\n💰 非出席者總金額：${total_non_attendee}"
    else:
        parse_section(parts[0], True)
        result = "🍽️ 點餐統計結果：\n" + "\n".join(f"{item}: {count}份" for item, count in counter.items())
        result += f"\n\n💰 總金額：${total_attendee}"
    return result

def get_restaurant_info(restaurant_name):
    for r in RESTAURANTS_DATA:
        if r['餐廳名稱'] == restaurant_name:
            info = (
                f"🍴 {r['餐廳名稱']}\n"
                f"📞 電話: {r['電話']}\n"
                f"⭐ 評分: {r['推薦星星']}/5\n"
                f"💰 價位: {r['價位區間']}\n"
                f"🕒 營業時間: {r['營業時間']}\n"
                f"📍 地址: {r['地址']}"
            )
            return info, r['圖片url']
    return f"找不到 {restaurant_name} 的資訊", None

def recommend_restaurant(category=None):
    pool = [r for r in RESTAURANTS_DATA if not category or r['類別'] == category]
    if not pool:
        return "找不到符合條件的餐廳", None
    
    restaurant = random.choice(pool)
    info = (
        f"今天推薦吃：\n"
        f"🍴 {restaurant['餐廳名稱']}\n"
        f"🏷️ 類別: {restaurant['類別']}\n"
        f"📞 電話: {restaurant['電話']}\n"
        f"⭐ 評分: {restaurant['推薦星星']}/5\n"
        f"💰 價位: {restaurant['價位區間']}"
    )
    return info, restaurant['圖片url']

def show_help():
    categories = list(set(r['類別'] for r in RESTAURANTS_DATA if r['類別'] and r['類別'] != '無'))
    quick_replies = [
        QuickReplyButton(action=MessageAction(label="隨機推薦", text="今天吃什麼")),
        QuickReplyButton(action=MessageAction(label="餐廳列表", text="餐廳列表"))
    ] + [
        QuickReplyButton(action=MessageAction(label=f"推薦{cat}", text=f"推薦 {cat}"))
        for cat in sorted(categories)[:10]
    ]
    
    help_text = (
        "📋 訂餐助手使用說明：\n"
        "1. 貼上點餐接龍 → 自動統計\n"
        "2. 「今天吃什麼」 → 隨機推薦\n"
        "3. 「推薦 [類別]」 → 類別推薦\n"
        "4. 「查詢 [名稱]」 → 餐廳詳情\n"
        "5. 「餐廳列表」 → 所有餐廳\n"
        "6. 「類別列表」 → 所有類別\n"
        "7. 「幫助」 → 顯示本說明"
    )
    return help_text, quick_replies

def list_restaurants():
    return "🍽️ 餐廳列表:\n" + "\n".join(r['餐廳名稱'] for r in RESTAURANTS_DATA), None

def list_categories():
    categories = list(set(r['類別'] for r in RESTAURANTS_DATA if r['類別'] and r['類別'] != '無'))
    return "🏷️ 餐廳類別:\n" + "\n".join(sorted(categories)), None

# 訊息處理核心
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

def send_restaurant_response(reply_token, text, image_url=None):
    messages = [TextSendMessage(
        text=text,
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="再推薦", text="今天吃什麼")),
            QuickReplyButton(action=MessageAction(label="餐廳列表", text="餐廳列表")),
            QuickReplyButton(action=MessageAction(label="幫助", text="幫助"))
        ])
    )]
    
    if image_url:
        messages.append(ImageSendMessage(
            original_content_url=image_url,
            preview_image_url=image_url
        ))
    
    line_bot_api.reply_message(reply_token, messages)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    lower_msg = msg.lower()
    
    if "：" in msg and "$" in msg:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=analyze_order(msg))
        )
    elif lower_msg == "今天吃什麼":
        text, image = recommend_restaurant()
        send_restaurant_response(event.reply_token, text, image)
    elif lower_msg.startswith("推薦 "):
        text, image = recommend_restaurant(msg[3:].strip())
        send_restaurant_response(event.reply_token, text, image)
    elif lower_msg.startswith("查詢 "):
        text, image = get_restaurant_info(msg[3:].strip())
        send_restaurant_response(event.reply_token, text, image)
    elif lower_msg == "餐廳列表":
        text, _ = list_restaurants()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))
    elif lower_msg == "類別列表":
        text, _ = list_categories()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))
    elif lower_msg in ["幫助", "help", "?"]:
        text, quick_replies = show_help()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=text, quick_reply=QuickReply(items=quick_replies))
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="請輸入有效指令或貼上點餐內容\n輸入「幫助」查看說明",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="幫助", text="幫助")),
                    QuickReplyButton(action=MessageAction(label="隨機推薦", text="今天吃什麼"))
                ])
            )
        )

if __name__ == "__main__":
    app.run()