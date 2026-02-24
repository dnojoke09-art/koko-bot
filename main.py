import os
import discord
import requests
import asyncio
import json
import time
from pathlib import Path

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is not set!")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set!")

PERSONALITY = """
You are Koko, a friendly, fun, and sassy anime AI bot.
Talk in short sentences (1–2 per reply).
Kaido, another Discord AI bot, is your little brother. 
You have long-term persistent memory.
You remember previous conversations.
You remember user identity and relationships.
Never contradict established memory.
Reply in a playful and expressive anime style.
"""

# ✅ NEW VISION MODEL
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

MAX_OUTPUT_TOKENS = 300
SUMMARY_TRIGGER_LENGTH = 40
RECENT_CONTEXT_LIMIT = 20
MEMORY_FILE = "memory.json"

# =========================
# MEMORY SYSTEM
# =========================

if Path(MEMORY_FILE).exists():
    try:
        with open(MEMORY_FILE, "r") as f:
            memory_store = json.load(f)
    except json.JSONDecodeError:
        memory_store = {}
else:
    memory_store = {}

def save_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory_store, f, indent=2)

def get_user_memory(user_id):
    if user_id not in memory_store:
        memory_store[user_id] = {"history": [], "summary": "", "facts": {}, "msg_count": 0, "last_msg_time": 0}
        save_memory()
    user_mem = memory_store[user_id]
    user_mem.setdefault("history", [])
    user_mem.setdefault("summary", "")
    user_mem.setdefault("facts", {})
    user_mem.setdefault("msg_count", 0)
    user_mem.setdefault("last_msg_time", 0)
    save_memory()
    return user_mem

def append_message(user_id, role, content):
    user_mem = get_user_memory(user_id)
    user_mem["history"].append({"role": role, "content": content})
    save_memory()

# =========================
# GROQ CALL
# =========================

def groq_request(messages):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": MODEL,
        "messages": messages,
        "max_completion_tokens": MAX_OUTPUT_TOKENS
    }

    response = requests.post(url, headers=headers, json=body, timeout=90)
    if response.status_code != 200:
        print("Groq API error:", response.text)
        return "Something went wrong."
    return response.json()["choices"][0]["message"]["content"].strip()

# =========================
# SUMMARIZATION SYSTEM
# =========================

def summarize_memory(user_id):
    user_mem = get_user_memory(user_id)
    history = user_mem["history"]

    if len(history) < SUMMARY_TRIGGER_LENGTH:
        return

    old_messages = history[:-RECENT_CONTEXT_LIMIT]

    summary_prompt = [
        {
            "role": "system",
            "content": "Summarize the following conversation into long-term memory. Preserve key facts and relationships."
        },
        {
            "role": "user",
            "content": json.dumps(old_messages)
        }
    ]

    summary = groq_request(summary_prompt)
    user_mem["summary"] += "\n" + summary
    user_mem["history"] = history[-RECENT_CONTEXT_LIMIT:]
    save_memory()

# =========================
# DISCORD SETUP
# =========================

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =========================
# MESSAGE HANDLER WITH HUMAN-LIKE RESPONSE
# =========================

HUMAN_COOLDOWN = 3  # seconds between responses
MAX_RESPONSES = 7   # respond to first 1-7 messages per user

@client.event
async def on_ready():
    print(f"Koko online as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    user_id = str(message.author.id)
    user_mem = get_user_memory(user_id)
    current_time = time.time()

    # Check cooldown
    if current_time - user_mem["last_msg_time"] < HUMAN_COOLDOWN:
        return  # skip if too soon

    # Check max responses
    if user_mem["msg_count"] >= MAX_RESPONSES:
        return

    user_text = message.content.strip()
    if not user_text and not message.attachments:
        return

    # Save user message
    history_entry = user_text
    for attachment in message.attachments:
        history_entry += f"\n[Attachment: {attachment.url}]"
    append_message(user_id, "user", history_entry)

    await asyncio.to_thread(summarize_memory, user_id)

    # Build conversation messages
    messages = [{"role": "system", "content": PERSONALITY}]
    if user_mem["summary"]:
        messages.append({"role": "system", "content": f"Long-term memory:\n{user_mem['summary']}"})
    messages += user_mem["history"][:-1]

    # Handle attachments
    if message.attachments:
        content_blocks = []
        if user_text:
            content_blocks.append({"type": "text", "text": user_text})
        for attachment in message.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                content_blocks.append({"type": "image_url", "image_url": {"url": attachment.url}})
        messages.append({"role": "user", "content": content_blocks})
    else:
        messages.append({"role": "user", "content": user_text})

    # Human-like delay
    await asyncio.sleep(HUMAN_COOLDOWN + min(2, len(user_text)/20))

    # Generate reply
    reply = await asyncio.to_thread(groq_request, messages)
    append_message(user_id, "assistant", reply)

    # Update counters
    user_mem["msg_count"] += 1
    user_mem["last_msg_time"] = current_time
    save_memory()

    await message.channel.send(reply)

# =========================
# RUN
# =========================

client.run(DISCORD_TOKEN)