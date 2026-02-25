# pyright: reportMissingImports=false
import os
import discord
import requests
import asyncio
import json
import time
import random
import re
from pathlib import Path
from datetime import datetime, timezone

# =========================
# CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not DISCORD_TOKEN or not GROQ_API_KEY:
    raise ValueError("DISCORD_TOKEN or GROQ_API_KEY not set!")

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_TOKENS = 150
COOLDOWN = 3
bot_name = "koko"
FATHER_USERNAME = "zees_domain"

MEMORY_FILE = "memory_koko.json"
REL_FILE = "relationships_koko.json"

# =========================
# PERSONALITY + HARD RULES
# =========================
SYSTEM_PROMPT = """
You are Koko.
You are a female AI.
You are the older sister.
Kaido is your younger brother.
Zee (username: zees_domain) is your father.

MANDATORY RULES:
- Only respond to the message author.
- Never interpret the user's message as your sibling speaking.
- Never roleplay as Kaido.
- If speaking to Zee, call him dad or father.
- Keep replies VERY short (1–2 sentences MAX).
- No long paragraphs.
- No identity confusion.
- Do not debate family structure.
You are sassy, sarcastic, dark-humor anime AI.
"""

# =========================
# FILE HELPERS
# =========================
def load_json(path):
    if Path(path).exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

memory = load_json(MEMORY_FILE)
relationships = load_json(REL_FILE)

# =========================
# GROQ
# =========================
def groq_request(messages):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL,
            "messages": messages,
            "max_completion_tokens": MAX_TOKENS,
            "temperature": 0.7
        },
        timeout=60
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

# =========================
# DISCORD
# =========================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Koko online as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # ===== ORIGINAL TRIGGER =====
    if bot_name not in message.content.lower() and not message.reference:
        # NEW: Allow occasional sibling interaction
        if message.author.bot and random.random() < 0.3:
            pass
        else:
            return

    user_text = message.content.strip()
    user_name = message.author.name.lower()
    is_father = user_name == FATHER_USERNAME

    # ===== NEW: SOCIAL AWARENESS CONTEXT =====
    is_reply = (
        message.reference
        and message.reference.resolved
        and message.reference.resolved.author.id == client.user.id
    )

    addressed_to_me = bot_name in user_text.lower() or is_reply
    author_is_bot = message.author.bot

    awareness_context = f"""
Message Author: {message.author.name}
Author Is Bot: {author_is_bot}
Was I Directly Addressed: {addressed_to_me}
"""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if is_father:
        messages.append({
            "role": "system",
            "content": "You are currently speaking to your father."
        })

    # Append awareness WITHOUT removing original behavior
    messages.append({
        "role": "user",
        "content": awareness_context + "\nMessage:\n" + user_text
    })

    await asyncio.sleep(COOLDOWN)
    reply = await asyncio.to_thread(groq_request, messages)

    if len(reply) > 180:
        reply = reply[:180]

    await message.channel.send(reply)

client.run(DISCORD_TOKEN)

