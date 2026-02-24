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
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not DISCORD_TOKEN or not GROQ_API_KEY:
    raise ValueError("DISCORD_TOKEN or GROQ_API_KEY not set!")

PERSONALITY = """You are Koko, a fun, sassy, sarcastic anime AI. 
You tell dark jokes, occasionally curse, keep replies short, remember users, relationships, and past conversations. 
Describe links/attachments if given."""

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_TOKENS = 300
MEMORY_FILE = "memory.json"
RELATIONSHIP_FILE = "relationships.json"
COOLDOWN = 3
bot_name = "koko"


# =========================
# DATA MANAGEMENT
# =========================
def load_json(file_path):
    try:
        if Path(file_path).exists():
            with open(file_path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
    return {}


memory_store = load_json(MEMORY_FILE)
relationships = load_json(RELATIONSHIP_FILE)
server_last_activity = {}


def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


# =========================
# USER MEMORY
# =========================
def get_user(user_id: str):
    if user_id not in memory_store:
        memory_store[user_id] = {
            "history": [],
            "summary": "",
            "facts": {},
            "msg_count": 0,
            "last_msg_time": 0,
            "user_style": {
                "lowercase": 0,
                "short": 0,
                "emoji": 0
            },
            "known_name": None,
            "username": None,
            "display_name": None,
            "emotional_score": 0,
            "last_convo": None,
            "streak": 0,
            "attachments": []
        }
        save_json(MEMORY_FILE, memory_store)
    return memory_store[user_id]


def append_message(user_id: str, role: str, content: str):
    user = get_user(user_id)
    user["history"].append({"role": role, "content": content})
    save_json(MEMORY_FILE, memory_store)


def summarize_memory(user_id: str):
    user = get_user(user_id)
    if len(user["history"]) < 40:
        return
    old_messages = user["history"][:-20]
    prompt = [{
        "role": "system",
        "content": "Summarize preserving key facts."
    }, {
        "role": "user",
        "content": json.dumps(old_messages)
    }]
    try:
        summary = groq_request(prompt)
        user["summary"] += "\n" + summary
        user["history"] = user["history"][-20:]
        save_json(MEMORY_FILE, memory_store)
    except Exception as e:
        print("Summarization error:", e)


# =========================
# STYLE & EMOTION
# =========================
def analyze_style(user_id: str, text: str):
    user = get_user(user_id)
    style = user.get("user_style", {"lowercase": 0, "short": 0, "emoji": 0})
    style["lowercase"] += int(text.islower())
    style["short"] += int(len(text.split()) <= 6)
    style["emoji"] += int(any(e in text for e in ["😂", "💀", "😭", "🔥"]))
    user["user_style"] = style

    # Emotional scoring
    pos_words = ["lol", "😂", "yay", "good", "fun"]
    neg_words = ["sad", "😢", "hate", "angry", "💀"]
    score = sum(1 for w in pos_words if w in text.lower()) - sum(
        1 for w in neg_words if w in text.lower())
    user["emotional_score"] += score

    # Conversation streak
    today = datetime.now(timezone.utc).date()
    last_convo = user.get("last_convo_date")
    if last_convo != str(today):
        if last_convo == str(today - timedelta(days=1)):
            user["streak"] = user.get("streak", 0) + 1
        else:
            user["streak"] = 1
        user["last_convo_date"] = str(today)

    save_json(MEMORY_FILE, memory_store)


# =========================
# URL HANDLING
# =========================
def extract_urls(text: str):
    return re.findall(r'https?://[^\s]+', text)


def fetch_url(url: str):
    try:
        r = requests.get(url,
                         timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for s in soup(["script", "style"]):
            s.extract()
        clean_text = "\n".join(line.strip()
                               for line in soup.get_text().splitlines()
                               if line.strip())
        return clean_text[:4000]
    except Exception as e:
        print("URL fetch error:", e)
        return "Could not retrieve content."


# =========================
# GROQ API
# =========================
def groq_request(messages):
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={
                              "Authorization": f"Bearer {GROQ_API_KEY}",
                              "Content-Type": "application/json"
                          },
                          json={
                              "model": MODEL,
                              "messages": messages,
                              "max_completion_tokens": MAX_TOKENS
                          },
                          timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except requests.RequestException as e:
        print("Groq API error:", e)
        return "Something went wrong."


# =========================
# RELATIONSHIPS
# =========================
REL_LEVELS = {
    0: "Stranger",
    1: "Familiar",
    2: "Friend",
    3: "Close",
    4: "Favorite"
}


def get_rel(user_id: str, username: str):
    if username.lower() == "zees_domain":
        return 999
    if user_id not in relationships:
        relationships[user_id] = {"level": 0, "xp": 0, "username": username}
    return relationships[user_id]["level"]


def add_rel_xp(user_id: str, username: str, amount: int = 1):
    if username.lower() == "zees_domain":
        return
    if user_id not in relationships:
        relationships[user_id] = {"level": 0, "xp": 0, "username": username}
    relationships[user_id]["xp"] += amount
    if relationships[user_id]["xp"] >= 15:
        relationships[user_id]["xp"] = 0
        relationships[user_id]["level"] += 1
    save_json(RELATIONSHIP_FILE, relationships)


def decay_relationships():
    for uid, data in relationships.items():
        if data["username"].lower() != "zees_domain":
            data["xp"] = max(data["xp"] - 1, 0)
            if data["xp"] == 0:
                data["level"] = max(data["level"] - 1, 0)
    save_json(RELATIONSHIP_FILE, relationships)


# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# =========================
# IDLE & RELATIONSHIP PINGS
# =========================
async def idle_task():
    await client.wait_until_ready()
    print("Idle task started ✅")
    while not client.is_closed():
        await asyncio.sleep(300)  # idle check interval
        t = time.time()
        for g in client.guilds:
            last = server_last_activity.get(g.id, 0)
            if t - last > 900:  # 15min no activity
                for c in g.text_channels:
                    if c.permissions_for(
                            g.me).send_messages and random.random() < 0.9:
                        try:
                            msg = await asyncio.to_thread(
                                groq_request, [{
                                    "role":
                                    "system",
                                    "content":
                                    PERSONALITY +
                                    "\nSpeak casually due to inactivity"
                                }])
                            await c.send(msg.strip())
                            server_last_activity[g.id] = time.time()
                            break
                        except Exception as e:
                            print("Idle task error:", e)
                            break


async def rel_ping_task():
    await client.wait_until_ready()
    print("Relationship ping task started ✅")
    while not client.is_closed():
        await asyncio.sleep(1)  # test interval
        for uid, data in relationships.items():
            level = data.get("level", 0)
            username = data.get("username", "").lower()
            if level >= 3 or username == "zees_domain":
                for g in client.guilds:
                    try:
                        member = await g.fetch_member(int(uid))
                        if member:
                            for c in g.text_channels:
                                if c.permissions_for(g.me).send_messages:
                                    await c.send(
                                        f"Hey {member.mention}, just checking in! 😏"
                                    )
                                    print(
                                        f"✅ Pinged {member.display_name} in {g.name}"
                                    )
                                    break
                    except discord.NotFound:
                        continue
                    except discord.Forbidden:
                        continue
                    except Exception as e:
                        print("Relationship ping error:", e)
                        continue


@client.event
async def on_ready():
    print(f"Koko online as {client.user} ✅")
    client.loop.create_task(idle_task())
    client.loop.create_task(rel_ping_task())


# =========================
# MESSAGE HANDLER
# =========================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    user_id = str(message.author.id)
    user_text = message.content.strip()
    user_mem = get_user(user_id)
    if message.guild:
        server_last_activity[message.guild.id] = time.time()

    # Discord identity
    user_mem["username"] = message.author.name
    user_mem["display_name"] = message.author.display_name
    save_json(MEMORY_FILE, memory_store)

    # Petname discomfort
    petnames = ["babe", "baby", "cutie", "sweetie", "honey"]
    uncomfortable = any(p in user_text.lower() for p in petnames) and get_rel(
        user_id, message.author.name) < 3

    # Should respond
    should_reply = (bot_name in user_text.lower()
                    or (message.reference and message.reference.resolved
                        and message.reference.resolved.author == client.user)
                    or random.random() < 0.6 or uncomfortable)
    if not should_reply:
        return
    if time.time(
    ) - user_mem["last_msg_time"] < COOLDOWN and not uncomfortable:
        return
    if not user_text and not message.attachments:
        return

    # Learn name
    name_match = re.search(r"(my name is|im|i am)\s+(\w+)", user_text.lower())
    if name_match:
        user_mem["known_name"] = name_match.group(2).capitalize()
        save_json(MEMORY_FILE, memory_store)

    analyze_style(user_id, user_text)
    add_rel_xp(user_id, message.author.name, 1)

    # URLs & attachments
    urls = extract_urls(user_text)
    url_ctx = ""
    for u in urls:
        url_ctx += f"\nContent from {u}:\n{fetch_url(u)}\n"

    history_entry = user_text + url_ctx
    for attachment in message.attachments:
        history_entry += f"\n[Attachment: {attachment.url}]"
    append_message(user_id, "user", history_entry)
    await asyncio.to_thread(summarize_memory, user_id)

    # Compose prompt
    messages = [{"role": "system", "content": PERSONALITY}]
    server_name = message.guild.name if message.guild else "DM"
    identity = f"You are in {server_name}, user: {user_mem['username']} ({user_mem['display_name']})"
    if user_mem.get("known_name"):
        identity += f", real name: {user_mem['known_name']}"
    messages.append({"role": "system", "content": identity})
    rel_lvl = get_rel(user_id, message.author.name)
    messages.append({
        "role":
        "system",
        "content":
        f"Relationship level: {REL_LEVELS.get(rel_lvl,'Stranger')}"
    })

    # Style mimic
    style = user_mem["user_style"]
    instr = "Mimic user's style."
    if style["lowercase"] > 5:
        instr += " lowercase."
    if style["short"] > 5:
        instr += " short messages."
    if style["emoji"] > 3:
        instr += " use emojis occasionally."
    messages.append({"role": "system", "content": instr})

    if user_mem["summary"]:
        messages.append({
            "role": "system",
            "content": "Memory:\n" + user_mem["summary"]
        })

    messages += user_mem["history"][:-1]

    if message.attachments:
        blocks = []
        if user_text:
            blocks.append({"type": "text", "text": user_text})
        for a in message.attachments:
            if a.content_type and "image" in a.content_type:
                blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": a.url
                    }
                })
        messages.append({"role": "user", "content": blocks})
    else:
        messages.append({"role": "user", "content": user_text})

    # Send request
    await asyncio.sleep(COOLDOWN + min(2, len(user_text) / 20))
    reply = await asyncio.to_thread(groq_request, messages)
    reply = reply.strip()
    if len(reply) > 200:
        reply = reply[:200] + "…"
    append_message(user_id, "assistant", reply)
    user_mem["msg_count"] += 1
    user_mem["last_msg_time"] = time.time()
    save_json(MEMORY_FILE, memory_store)

    # Respond
    if uncomfortable:
        reply = "Um… I don’t like being called that 😳 " + reply
    await message.channel.send(reply)


# =========================
# RUN BOT
# =========================
client.run(DISCORD_TOKEN)
