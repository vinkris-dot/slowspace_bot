#!/usr/bin/env python3
"""
MindFlow Telegram Bot – multi-žingsnis
1. Išpilk – laisva mintis
2. Išgryninimas – botas klausia 2-3 klausimų
3. Struktūra – parenka formą
4. Rezultatas – paruoštas dokumentas
"""

import json
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    ConversationHandler, filters, ContextTypes
)
import anthropic

# === NUSTATYMAI ===
TELEGRAM_TOKEN = "8783209011:AAEZnxEkW0ndy2nnhxY3QzFci7fkh-HzDHQ"
ANTHROPIC_API_KEY = "ĮDĖK_NAUJĄ_ANTHROPIC_RAKTĄ"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Pokalbio būsenos
WAITING_THOUGHT = 0
WAITING_ANSWERS = 1
WAITING_FORMAT = 2

# ===== PROMPTS =====

CLARIFY_PROMPT = """Vartotojas pateikė nestruktūruotą mintį lietuvių kalba. 
Tavo užduotis – užduoti 2-3 tikslinančius klausimus, kad geriau suprastum ko jis nori.

Klausimai turi būti trumpi, konkretūs, lietuviškai.
Atsakyk TIKTAI JSON formatu:
{
  "type": "idea|plan|insight|stress|question",
  "questions": ["klausimas 1", "klausimas 2", "klausimas 3"]
}"""

FORMAT_PROMPT = """Remdamasis pradine mintimi ir atsakymais į klausimus, nuspręsk kokio formato rezultatas tinkamiausias.

Galimi formatai:
- koncepcija – idėja su pagrindiniais principais
- planas – žingsniai su terminais
- pristatymas – struktūra slide'ams
- straipsnis – teksto struktūra
- veiksmų_planas – trumpas TODO sąrašas

Atsakyk TIKTAI JSON formatu:
{
  "format": "koncepcija|planas|pristatymas|straipsnis|veiksmų_planas",
  "reason": "kodėl šis formatas tinka (1 sakinys)"
}"""

RESULT_PROMPT = """Sukurk pilną, paruoštą rezultatą lietuvių kalba pagal:
- Pradinę mintį
- Atsakymus į klausimus  
- Pasirinktą formatą

Rezultatas turi būti realiai naudojamas – ne eskizas, o paruoštas dokumentas.
Naudok aiškią struktūrą su antraštėmis. Rašyk konkrečiai, be vandens."""

FORMAT_BUTTONS = [
    ["📋 Koncepcija", "📅 Planas"],
    ["🎯 Pristatymas", "📝 Straipsnis"],
    ["✅ Veiksmų planas"],
]

FORMAT_MAP = {
    "📋 Koncepcija": "koncepcija",
    "📅 Planas": "planas",
    "🎯 Pristatymas": "pristatymas",
    "📝 Straipsnis": "straipsnis",
    "✅ Veiksmų planas": "veiksmų_planas",
}

TYPE_ICONS = {
    "idea": "◈", "plan": "▦", "insight": "◉", "stress": "◌", "question": "?"
}

# ===== HANDLERS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Sveika! Aš *MindFlow* – mintis paversiu į medžiagą.\n\n"
        "Išpilk kas galvoje – laisvai, be struktūros 👇",
        parse_mode="Markdown"
    )
    return WAITING_THOUGHT

async def receive_thought(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thought = update.message.text.strip()
    context.user_data["thought"] = thought
    context.user_data["history"] = [{"role": "user", "content": thought}]

    await update.message.reply_text("⏳ Analizuoju...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=CLARIFY_PROMPT,
            messages=[{"role": "user", "content": thought}],
        )
        text = response.content[0].text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)

        context.user_data["type"] = data.get("type", "idea")
        context.user_data["questions"] = data.get("questions", [])
        context.user_data["answers"] = []
        context.user_data["q_index"] = 0

        icon = TYPE_ICONS.get(data.get("type", "idea"), "~")
        questions = data.get("questions", [])

        if questions:
            await update.message.reply_text(
                f"{icon} Supratau. Keletas klausimų:\n\n*{questions[0]}*",
                parse_mode="Markdown"
            )
            return WAITING_ANSWERS
        else:
            return await generate_format_choice(update, context)

    except Exception as e:
        logger.error(f"Klaida: {e}")
        await update.message.reply_text("⚠️ Klaida. Bandyk dar kartą.")
        return WAITING_THOUGHT

async def receive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip()
    context.user_data["answers"].append(answer)

    questions = context.user_data.get("questions", [])
    q_index = context.user_data.get("q_index", 0) + 1
    context.user_data["q_index"] = q_index

    if q_index < len(questions):
        await update.message.reply_text(
            f"*{questions[q_index]}*",
            parse_mode="Markdown"
        )
        return WAITING_ANSWERS
    else:
        return await generate_format_choice(update, context)

async def generate_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thought = context.user_data.get("thought", "")
    answers = context.user_data.get("answers", [])
    questions = context.user_data.get("questions", [])

    qa_text = "\n".join([f"K: {q}\nA: {a}" for q, a in zip(questions, answers)])
    combined = f"Mintis: {thought}\n\nKlausimai ir atsakymai:\n{qa_text}"
    context.user_data["combined"] = combined

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system=FORMAT_PROMPT,
            messages=[{"role": "user", "content": combined}],
        )
        text = response.content[0].text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        suggested = data.get("format", "")
        reason = data.get("reason", "")

        context.user_data["suggested_format"] = suggested

        keyboard = ReplyKeyboardMarkup(FORMAT_BUTTONS, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            f"📌 Siūlau: *{suggested}*\n_{reason}_\n\nArba pasirink kitą:",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return WAITING_FORMAT

    except Exception as e:
        logger.error(f"Format klaida: {e}")
        keyboard = ReplyKeyboardMarkup(FORMAT_BUTTONS, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Pasirink formatą:", reply_markup=keyboard)
        return WAITING_FORMAT

async def receive_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    fmt = FORMAT_MAP.get(choice, context.user_data.get("suggested_format", "koncepcija"))
    combined = context.user_data.get("combined", "")

    await update.message.reply_text("⏳ Kuriu rezultatą...", reply_markup=ReplyKeyboardRemove())

    try:
        prompt = f"{combined}\n\nFormatas: {fmt}"
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=RESULT_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text

        await update.message.reply_text(result)
        await update.message.reply_text(
            "✅ Paruošta.\n\nNauja mintis? Tiesiog rašyk 👇"
        )

        context.user_data.clear()
        return WAITING_THOUGHT

    except Exception as e:
        logger.error(f"Result klaida: {e}")
        await update.message.reply_text("⚠️ Klaida generuojant rezultatą. Bandyk /start")
        return WAITING_THOUGHT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Atšaukta. Rašyk /start pradėti iš naujo.")
    return ConversationHandler.END

# ===== MAIN =====

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_thought),
        ],
        states={
            WAITING_THOUGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_thought)],
            WAITING_ANSWERS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answer)],
            WAITING_FORMAT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_format)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    logger.info("MindFlow botas paleistas...")
    app.run_polling()

if __name__ == "__main__":
    main()
