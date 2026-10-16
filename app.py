import os
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# Environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# Initialize Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Chat memory store
SESSIONS = {}
MAX_HISTORY_TURNS = 10

def chat_with_memory(sender_id: str, new_message: str) -> str:
    if sender_id not in SESSIONS:
        SESSIONS[sender_id] = []

    SESSIONS[sender_id].append({
        "role": "user",
        "parts": [{"text": new_message}]
    })

    if len(SESSIONS[sender_id]) > MAX_HISTORY_TURNS:
        SESSIONS[sender_id] = SESSIONS[sender_id][-MAX_HISTORY_TURNS:]

    system_prompt = (
        "You are an automated WhatsApp customer assistant. "
        "Keep responses polite, natural, and concise."
    )

    response = ai_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=SESSIONS[sender_id],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7
        )
    )

    reply_text = response.text

    SESSIONS[sender_id].append({
        "role": "model",
        "parts": [{"text": reply_text}]
    })

    return reply_text

def send_whatsapp_message(to_number: str, message_text: str):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }
    response = requests.post(url, headers=headers, json=payload)
    print("WhatsApp API Status:", response.status_code, response.text)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def webhook_handler():
    data = request.get_json()

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if messages:
            message = messages[0]
            if message.get("type") == "text":
                sender_id = message.get("from")
                user_text = message.get("text", {}).get("body", "")

                bot_response = chat_with_memory(sender_id, user_text)
                send_whatsapp_message(sender_id, bot_response)

    except Exception as e:
        print("Error handling message:", e)

    return jsonify({"status": "received"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
