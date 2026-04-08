#!/usr/bin/env python3
"""
MindFlow Telegram Bot – galutinė versija
1. Išpilk – laisva mintis
2. Išgryninimas – 1-2 tikslūs klausimai
3. Formatas – botas siūlo, tu patvirtini
4. Rezultatas – glaustas branduolys + plėtimo pasiūlymas
"""

import os
import json
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    ConversationHandler, filters, ContextTypes
)
import anthropic

# === RAKTAI – keisk tik čia ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Būsenos
WAITING_THOUGHT = 0
WAITING_ANSWER  = 1
WAITING_FORMAT  = 2
WAITING_EXPAND  = 3

# ===== PROMPTS =====

CLARIFY_PROMPT = """\
Vartotojas pateikė mintį lietuvių kalba. Užduok VIENĄ geriausią tikslinantį klausimą.

Taisyklės:
- Klausimas turi būti konkretus, ne abstraktus
- Jei mintis jau pakankamai aiški – klausimų nereikia, grąžink tuščią sąrašą
- Klausimas lietuviškai, be ceremonijų

Atsakyk tik JSON:
{
  "type": "idea|plan|insight|stress|question",
  "question": "vienas klausimas arba tuščias string jei nereikia"
}"""

FORMAT_PROMPT = """\
Remdamasis mintimi ir atsakymu nuspręsk geriausią formatą.

Formatai:
- koncepcija – idėja su principais (kai tema nauja, neaiški)
- planas – žingsniai su terminais (kai aišku ką daryti)
- pristatymas – struktūra slide'ams (kai reikia kitiems pristatyti)
- straipsnis – teksto struktūra (kai reikia rašyti)
- veiksmai – trumpas TODO (kai konkreti užduotis)

Atsakyk tik JSON:
{
  "format": "koncepcija|planas|pristatymas|straipsnis|veiksmai",
  "reason": "kodėl šis formatas – vienas sakinys"
}"""

RESULT_PROMPT = """\
Sukurk GLAUSTĄ rezultatą lietuvių kalba. Ne ilgiau kaip 300 žodžių.

Struktūra:
- Vienas stiprus įvadinis sakinys kas tai yra
- 3-5 pagrindiniai elementai (priklausomai nuo formato)
- Vienas konkretus pirmas žingsnis

Rašyk konkrečiai. Be vandens. Be perteklinių antraščių.
Naudok tik Telegram Markdown: *bold* kursyvui nenaudok, - sąrašams."""

EXPAND_PROMPT = """\
Vartotojas nori plėsti konkrečią dalį. Išplėsk ją – išsamiai, bet tik tą dalį.
Rašyk lietuviškai, konkrečiai, naudok Telegram Markdown: *bold*, - sąrašams."""

FORMAT_BUTTONS = [
    ["📋 Koncepcija", "📅 Planas"],
    ["🎯 Pristatymas", "📝 Straipsnis"],
    ["✅ Veiksmai"],
]

FORMAT_MAP = {
    "📋 Koncepcija": "koncepcija",
    "📅 Planas": "planas",
    "🎯 Pristatymas": "pristatymas",
    "📝 Straipsnis": "straipsnis",
    "✅ Veiksmai": "veiksmai",
}

FORMAT_ICONS = {
    "koncepcija": "📋",
    "planas": "📅",
    "pristatymas": "🎯",
    "straipsnis": "📝",
    "veiksmai": "✅",
}

TYPE_ICONS = {
    "idea": "◈", "plan": "▦", "insight": "◉", "stress": "◌", "question": "?"
}

def escape_md(text):
    chars = r'_[]()~`>#+=|{}.!'
    for c in chars:
        text = text.replace(c, f'\\{c}')
    return text

def call_claude(system, user_content, max_tokens=1000):
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text

def parse_json(text):
    clean = text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

# ===== HANDLERS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Sveika\\! Aš *MindFlow*\\.\n\nIšpilk kas galvoje – laisvai, be struktūros 👇",
        parse_mode="MarkdownV2"
    )
    return WAITING_THOUGHT

async def receive_thought(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thought = update.message.text.strip()
    context.user_data["thought"] = thought

    await update.message.reply_text("⏳")

    try:
        text = call_claude(CLARIFY_PROMPT, thought, max_tokens=300)
        data = parse_json(text)

        context.user_data["type"] = data.get("type", "idea")
        question = data.get("question", "").strip()

        if question:
            context.user_data["question"] = question
            icon = TYPE_ICONS.get(data.get("type", "idea"), "~")
            await update.message.reply_text(
                f"{icon} *{question}*",
                parse_mode="Markdown"
            )
            return WAITING_ANSWER
        else:
            return await ask_format(update, context, "")

    except Exception as e:
        logger.error(f"Klaida: {e}")
        await update.message.reply_text("⚠️ Klaida. Bandyk /start")
        return WAITING_THOUGHT

async def receive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip()
    context.user_data["answer"] = answer
    return await ask_format(update, context, answer)

async def ask_format(update, context, answer):
    thought = context.user_data.get("thought", "")
    question = context.user_data.get("question", "")
    combined = f"Mintis: {thought}"
    if question and answer:
        combined += f"\nKlausimas: {question}\nAtsakymas: {answer}"
    context.user_data["combined"] = combined

    try:
        text = call_claude(FORMAT_PROMPT, combined, max_tokens=200)
        data = parse_json(text)
        fmt = data.get("format", "koncepcija")
        reason = data.get("reason", "")
        icon = FORMAT_ICONS.get(fmt, "📋")
        context.user_data["suggested_format"] = fmt

        keyboard = ReplyKeyboardMarkup(FORMAT_BUTTONS, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            f"📌 Siūlau: *{fmt}*\n_{reason}_\n\nArba pasirink kitą:",
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
    context.user_data["format"] = fmt
    combined = context.user_data.get("combined", "")

    await update.message.reply_text("⏳ Kuriu...", reply_markup=ReplyKeyboardRemove())

    try:
        prompt = f"{combined}\n\nFormatas: {fmt}"
        result = call_claude(RESULT_PROMPT, prompt, max_tokens=800)
        context.user_data["result"] = result

        expand_keyboard = ReplyKeyboardMarkup(
            [["🔍 Išplėsk", "✅ Gerai, baigta"]],
            one_time_keyboard=True, resize_keyboard=True
        )

        await update.message.reply_text(result, parse_mode="Markdown")
        await update.message.reply_text(
            "Kurią dalį plėsti, ar baigta?",
            reply_markup=expand_keyboard
        )
        return WAITING_EXPAND

    except Exception as e:
        logger.error(f"Result klaida: {e}")
        await update.message.reply_text("⚠️ Klaida. Bandyk /start")
        return WAITING_THOUGHT

async def receive_expand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()

    if choice == "✅ Gerai, baigta":
        context.user_data.clear()
        await update.message.reply_text(
            "✅ Paruošta\\. Nauja mintis? Tiesiog rašyk 👇",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardRemove()
        )
        return WAITING_THOUGHT

    result = context.user_data.get("result", "")
    combined = context.user_data.get("combined", "")

    await update.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())

    try:
        prompt = f"Originalus rezultatas:\n{result}\n\nVartotojas nori plėsti: {choice}\n\nKontekstas: {combined}"
        expanded = call_claude(EXPAND_PROMPT, prompt, max_tokens=1000)

        expand_keyboard = ReplyKeyboardMarkup(
            [["🔍 Išplėsk dar", "✅ Gerai, baigta"]],
            one_time_keyboard=True, resize_keyboard=True
        )
        await update.message.reply_text(expanded, parse_mode="Markdown")
        await update.message.reply_text("Dar plėsti, ar baigta?", reply_markup=expand_keyboard)
        return WAITING_EXPAND

    except Exception as e:
        logger.error(f"Expand klaida: {e}")
        await update.message.reply_text("⚠️ Klaida plečiant.")
        return WAITING_EXPAND

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Atšaukta. /start – pradėti iš naujo.", reply_markup=ReplyKeyboardRemove())
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
            WAITING_THOUGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_thought)],
            WAITING_ANSWER:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answer)],
            WAITING_FORMAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_format)],
            WAITING_EXPAND:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_expand)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    logger.info("MindFlow botas paleistas...")
    app.run_polling(drop_pending_updates=True)

main()
