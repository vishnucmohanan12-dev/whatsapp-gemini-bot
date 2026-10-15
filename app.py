import os
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_token_123")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Chat memory store
SESSIONS = {}
MAX_HISTORY_TURNS = 10

@app.route("/", methods=["GET"])
def home():
    return "Bot is running!", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            message = entry["messages"][0]
            sender_id = message["from"]

            if message.get("type") == "text":
                user_text = message["text"]["body"]

                if user_text.strip().lower() in ["reset", "clear"]:
                    SESSIONS[sender_id] = []
                    send_whatsapp_message(sender_id, "Conversation reset!")
                    return jsonify({"status": "reset"}), 200

                bot_reply = chat_with_memory(sender_id, user_text)
                send_whatsapp_message(sender_id, bot_reply)

    except Exception as e:
        print(f"Error handling message: {e}")

    return jsonify({"status": "success"}), 200

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
        "Keep responses polite, natural, and concise (under 2-3 short paragraphs)."
    )

    response = ai_client.models.generate_content(
        model="gemini-1.5-flash",
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
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text},
    }
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
