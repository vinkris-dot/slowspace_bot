#!/usr/bin/env python3
"""
SlowSpace Telegram Bot - Multi-step version
Mintys → Klausimai → Rezultatas
"""

import os
import json
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

import anthropic

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Saugome pokalbio būseną kiekvienam vartotojui
user_state = {}

CLARIFY_PROMPT = """Tu esi kūrybinio mąstymo partneris. Vartotojas dalijasi mintimi lietuvių kalba.

Tavo užduotis: užduoti VIENĄ tikslinantį klausimą kad geriau suprastum ko reikia.

Klausk apie:
- Kokiam tikslui tai skirta?
- Kas yra auditorija?
- Koks formatas reikalingas?

Atsakyk tik vienu trumpu klausimu lietuviškai. Be jokių įžangų."""

RESULT_PROMPT = """Tu esi kūrybinio mąstymo partneris. Vartotojas davė mintį ir atsakė į tikslinantį klausimą.

Paversk tai į struktūruotą rezultatą lietuviškai.

Atsakyk TIKTAI JSON formatu:
{
  "type": "idea|plan|insight|stress|question",
  "title": "trumpas pavadinimas iki 6 žodžių",
  "summary": "vienas sakinys kas tai yra",
  "structured": "struktūruota forma - žingsniai arba pastabos, kiekvienas su brūkšneliu naujoje eilutėje",
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
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        return

    state = user_state.get(user_id, {"step": "initial"})

    if state["step"] == "initial":
        # Pirma mintis – klausiame tikslinančio klausimo
        await update.message.reply_text("⏳ Apdorojama...")
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=CLARIFY_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            question = response.content[0].text.strip()
            user_state[user_id] = {"step": "clarify", "raw": text}
            await update.message.reply_text(question)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Klaida: {str(e)}")

    elif state["step"] == "clarify":
        # Atsakymas į klausimą – generuojame rezultatą
        raw = state["raw"]
        await update.message.reply_text("⏳ Kuriu rezultatą...")
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system=RESULT_PROMPT,
                messages=[
                    {"role": "user", "content": f"Mintis: {raw}\nAtsakymas: {text}"}
                ],
            )
            result_text = response.content[0].text
            clean = result_text.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)
            reply = format_result(result, raw)
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Klaida: {str(e)}")
        finally:
            user_state[user_id] = {"step": "initial"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "initial"}
    await update.message.reply_text(
        "👋 Sveika! Aš *SlowSpace* botas.\n\n"
        "Išpilk kas galvoje – aš paklausiu vieno klausimo ir paversiu į struktūruotą formą.\n\n"
        "Rašyk laisvai lietuviškai 👇",
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
