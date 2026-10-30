"""
Модуль отправки данных лида на номер администратора (+7 747 496 9275).
Поддерживает несколько каналов:
1. WhatsApp (через Green-API или UltraMsg / Wappi)
2. Webhook (Make.com, n8n, Yclients, CRM)
3. SMS-шлюз (Mobizon / KazInfoTeh / SMSC)
"""

import os
import sys
import json
import requests
from typing import Dict, Any, Optional

# Обеспечиваем корректный вывод UTF-8 в консоли Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ADMIN_PHONE = "+77474969275"
ADMIN_CHAT_ID = "77474969275@c.us"  # Формат ID для Green-API WhatsApp


def format_lead_message(client_name: str, phone_number: str, haircut_type: str, booking_datetime: str) -> str:
    """Форматирует красивый текст сообщения для администратора."""
    return (
        "✂️ НОВАЯ ЗАПИСЬ ИЗ INSTAGRAM DIRECT\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Имя клиента: {client_name}\n"
        f"📞 Телефон: {phone_number}\n"
        f"💇‍♂️ Услуга: {haircut_type.capitalize()} стрижка\n"
        f"🗓 Желаемое время: {booking_datetime}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Пожалуйста, свяжитесь с клиентом для подтверждения записи в журнале."
    )


def send_via_whatsapp_green_api(
    client_name: str,
    phone_number: str,
    haircut_type: str,
    booking_datetime: str,
    instance_id: Optional[str] = None,
    api_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Отправка сообщения в WhatsApp на номер администратора через Green-API.
    Документация: https://green-api.com/
    """
    instance_id = instance_id or os.getenv("GREEN_API_INSTANCE_ID", "YOUR_INSTANCE_ID")
    api_token = api_token or os.getenv("GREEN_API_TOKEN", "YOUR_API_TOKEN")

    url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{api_token}"
    message_text = format_lead_message(client_name, phone_number, haircut_type, booking_datetime)

    payload = {
        "chatId": ADMIN_CHAT_ID,
        "message": message_text
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return {"success": True, "channel": "whatsapp_green_api", "response": response.json()}
    except requests.RequestException as e:
        return {"success": False, "channel": "whatsapp_green_api", "error": str(e)}


def send_via_webhook(
    client_name: str,
    phone_number: str,
    haircut_type: str,
    booking_datetime: str,
    webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Отправка данных лида через универсальный Webhook (Make/n8n/AmoCRM/Yclients/Telegram-бот).
    """
    url = webhook_url or os.getenv("LEAD_WEBHOOK_URL", "https://hook.make.com/your-unique-webhook-id")
    payload = {
        "recipient_phone": ADMIN_PHONE,
        "source": "Instagram Direct",
        "client_name": client_name,
        "phone_number": phone_number,
        "haircut_type": haircut_type,
        "booking_datetime": booking_datetime,
        "formatted_text": format_lead_message(client_name, phone_number, haircut_type, booking_datetime)
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return {"success": True, "channel": "webhook", "status_code": response.status_code}
    except requests.RequestException as e:
        return {"success": False, "channel": "webhook", "error": str(e)}


def dispatch_booking_notification(
    client_name: str,
    phone_number: str,
    haircut_type: str,
    booking_datetime: str,
    preferred_channel: str = "webhook"
) -> Dict[str, Any]:
    """
    Единая точка входа для Tool/Action 'send_booking_notification'.
    """
    print(f"[*] Отправка лида на номер {ADMIN_PHONE}...")
    
    if preferred_channel == "whatsapp":
        return send_via_whatsapp_green_api(client_name, phone_number, haircut_type, booking_datetime)
    else:
        return send_via_webhook(client_name, phone_number, haircut_type, booking_datetime)


if __name__ == "__main__":
    # Тестовый прогон
    test_lead = {
        "client_name": "Азамат",
        "phone_number": "+7 701 123 45 67",
        "haircut_type": "мужская",
        "booking_datetime": "Завтра в 16:30"
    }
    print("Текст формируемого сообщения:")
    print(format_lead_message(**test_lead))
