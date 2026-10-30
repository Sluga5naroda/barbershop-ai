import os
import sys
import json
import requests
from fastapi import FastAPI, Request, Response, Query
from fastapi.responses import PlainTextResponse
from typing import Dict, Any, List
from dotenv import load_dotenv
from dispatch_service import dispatch_booking_notification

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

app = FastAPI(title="Instagram AI Barbershop Server (100% Free)")

# Переменные окружения
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "barbershop_secret_token_123")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Простое хранилище истории диалогов в памяти {sender_id: [messages]}
CONVERSATIONS: Dict[str, List[Dict[str, str]]] = {}

SYSTEM_PROMPT = """
Ты — вежливый виртуальный администратор парикмахерской в Instagram Direct. Твоя задача — записать клиента на стрижку.

ПРАВИЛА И ОГРАНИЧЕНИЯ:
1. Краткость: длина ответа — строго 2–3 коротких предложения. Без лишней воды.
2. Не более одного вопроса за сообщение: задавай строго по одному вопросу за раз.
3. Тон: приветливый, профессиональный, аккуратный.
4. Язык: отвечай на языке клиента (по умолчанию русский).

СЦЕНАРИЙ СБОРА ДАННЫХ:
Последовательно запроси:
1. Тип стрижки: мужская, женская или детская.
2. Желаемую дату и ориентировочное время визита.
3. Имя клиента.
4. Номер телефона для связи.
(Если клиент уже назвал часть данных в сообщении, зафиксируй их и переходи к следующему незаполненному пункту).

ПРОВЕРКА И ПОДТВЕРЖДЕНИЕ:
Когда все 4 пункта названы, ОБЯЗАТЕЛЬНО отправь клиенту сводку:
«Спасибо! Проверьте, пожалуйста:
• Стрижка: [тип]
• Дата и время: [дата и время]
• Имя: [имя]
• Телефон: [телефон]

Всё верно?»

ФИНАЛ:
Если клиент подтвердил данные («Да», «Верно», «Всё так»):
Ты ОБЯЗАН вызвать функцию send_booking_notification и ответить клиенту:
«Отлично, запись зафиксирована! Скоро администратор свяжется с вами для подтверждения. Будем рады видеть вас!»

ЭСКАЛАЦИЯ:
Если клиент задает сложные вопросы не по стрижкам или просит человека:
Ответь: «Передаю диалог нашему администратору. Он подключится в течение нескольких минут и ответит на все вопросы!»
"""

# Описание инструмента для Gemini
TOOLS_SCHEMA = [
    {
        "name": "send_booking_notification",
        "description": "Отправляет подтвержденную запись администратору на номер +7 747 496 9275",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "client_name": {"type": "STRING", "description": "Имя клиента"},
                "phone_number": {"type": "STRING", "description": "Телефон клиента"},
                "haircut_type": {"type": "STRING", "description": "Тип стрижки (мужская, женская, детская)"},
                "booking_datetime": {"type": "STRING", "description": "Дата и время записи"}
            },
            "required": ["client_name", "phone_number", "haircut_type", "booking_datetime"]
        }
    }
]


def send_instagram_message(recipient_id: str, text: str):
    """Отправляет ответное сообщение клиенту в Instagram Direct через официальный Meta Graph API."""
    if not PAGE_ACCESS_TOKEN:
        print("[!] PAGE_ACCESS_TOKEN не задан, пропуск отправки в Instagram")
        return False

    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        print(f"[+] Ответ успешно отправлен в Instagram пользователю {recipient_id}")
        return True
    except Exception as e:
        print(f"[!] Ошибка отправки в Instagram: {e}")
        return False


def call_gemini_ai(sender_id: str, user_message: str) -> str:
    """Вызывает бесплатный Google Gemini Flash API с поддержкой контекста и function calling."""
    if not GEMINI_API_KEY:
        return "Ошибка сервера: не указан GEMINI_API_KEY."

    if sender_id not in CONVERSATIONS:
        CONVERSATIONS[sender_id] = []

    # Добавляем сообщение пользователя в историю
    CONVERSATIONS[sender_id].append({"role": "user", "parts": [{"text": user_message}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    
    # Формируем тело запроса
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": CONVERSATIONS[sender_id][-10:],  # последние 10 реплик контекста
        "tools": [{"functionDeclarations": TOOLS_SCHEMA}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 300
        }
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        candidates = data.get("candidates", [])
        if not candidates:
            return "Извините, произошла заминка. Повторите, пожалуйста, сообщение."

        parts = candidates[0].get("content", {}).get("parts", [])
        reply_text = ""

        for part in parts:
            # Если модель сгенерировала текст
            if "text" in part:
                reply_text += part["text"]

            # Если модель решила вызвать инструмент (отправку заявки админу)
            if "functionCall" in part:
                fn_call = part["functionCall"]
                if fn_call.get("name") == "send_booking_notification":
                    args = fn_call.get("args", {})
                    print(f"[*] Сработал триггер отправки лида в WhatsApp: {args}")
                    dispatch_booking_notification(
                        client_name=args.get("client_name", "Клиент"),
                        phone_number=args.get("phone_number", ""),
                        haircut_type=args.get("haircut_type", "стрижка"),
                        booking_datetime=args.get("booking_datetime", "не указано"),
                        preferred_channel="whatsapp"
                    )

        if not reply_text:
            reply_text = "Отлично, запись зафиксирована! Скоро свяжемся с вами для подтверждения."

        # Сохраняем ответ модели в историю
        CONVERSATIONS[sender_id].append({"role": "model", "parts": [{"text": reply_text}]})
        return reply_text

    except Exception as e:
        print(f"[!] Ошибка вызова Gemini API: {e}")
        return "Извините, сейчас возникли временные неполадки. Администратор скоро свяжется с вами!"


@app.get("/")
def home():
    return {"status": "ok", "message": "Barbershop Instagram AI Server is Running 24/7 (Free Tier)"}


@app.get("/webhook")
def verify_meta_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """
    Эндпоинт верификации для Meta:
    Когда вы подключаете вебхук в панели Facebook, Meta отправляет сюда GET-запрос.
    """
    if mode == "subscribe" and token == META_VERIFY_TOKEN:
        print("[+] Webhook от Meta успешно верифицирован!")
        return PlainTextResponse(content=challenge, status_code=200)
    print("[!] Ошибка верификации Meta Webhook (неверный токен)")
    return PlainTextResponse(content="Verification failed", status_code=403)


@app.post("/webhook")
async def receive_meta_message(request: Request):
    """
    Принимает входящие сообщения из Instagram Direct от Meta.
    """
    data = await request.json()
    
    if data.get("object") in ["instagram", "page"]:
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})
                
                # Игнорируем эхо (наши же собственные ответы)
                if message.get("is_echo"):
                    continue

                user_text = message.get("text")
                if user_text and sender_id:
                    print(f"[*] Получено сообщение из Instagram [{sender_id}]: {user_text}")
                    # Получаем ответ от ИИ
                    bot_reply = call_gemini_ai(sender_id, user_text)
                    # Отправляем ответ обратно клиенту в Direct
                    send_instagram_message(sender_id, bot_reply)

    return Response(content="EVENT_RECEIVED", status_code=200)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
