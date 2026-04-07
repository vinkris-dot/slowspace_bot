#!/usr/bin/env python3
"""
MindFlow Telegram Bot
Mintys → Medžiaga

Reikalavimai:
  pip install python-telegram-bot anthropic

Railway environment variables:
  TELEGRAM_TOKEN
  ANTHROPIC_API_KEY
"""

import os
import json
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

# === NUSTATYMAI (iš environment variables) ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ANTHROPIC ===
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Tu esi kūrybinio mąstymo partneris. Vartotojas duoda nestruktūruotą mintį lietuvių kalba.

Atsakyk TIKTAI JSON formatu be jokio papildomo teksto:
{
  "type": "idea|plan|insight|stress|question",
  "title": "trumpas pavadinimas iki 6 žodžių lietuviškai",
  "summary": "vienas sakinys kas tai yra",
  "structured": "struktūruota forma - žingsniai arba pastabos, kiekvienas elementas naujoje eilutėje su brūkšneliu",
  "next": "vienas konkretus kitas žingsnis"
}"""

TYPE_LABELS = {
    "idea":     ("◈", "Idėja"),
    "plan":     ("▦", "Planas"),
    "insight":  ("◉", "Įžvalga"),
    "stress":   ("◌", "Stresas"),
    "question": ("?", "Klausimas"),
}

def format_result(result: dict, raw: str) -> str:
    t = result.get("type", "idea")
    icon, label = TYPE_LABELS.get(t, ("~", "Mintis"))
    lines = [
        f"{icon} *{label.upper()}*",
        f"*{result.get('title', '')}*",
        "",
        f"_{result.get('summary', '')}_",
        "",
        result.get("structured", ""),
        "",
        "→ *Kitas žingsnis:*",
        result.get("next", ""),
        "",
        f"💬 _{raw}_",
    ]
    return "\n".join(lines)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if not raw:
        return
    await update.message.reply_text("⏳ Apdorojama...")
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": raw}],
        )
        text = response.content[0].text
        clean = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        reply = format_result(result, raw)
        await update.message.reply_text(reply, parse_mode="Markdown")
    except json.JSONDecodeError:
        await update.message.reply_text(f"⚠️ Nepavyko apdoroti. Bandyk dar kartą.")
    except Exception as e:
        logger.error(f"Klaida: {e}")
        await update.message.reply_text(f"⚠️ Klaida: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Sveika! Aš *SlowSpace* botas.\n\n"
        "Išpilk kas galvoje – aš paversiu į struktūruotą formą.\n\n"
        "Tiesiog rašyk laisvai lietuviškai 👇",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("SlowSpace botas paleistas...")
    app.run_polling()

if __name__ == "__main__":
    main()
