import os, logging

for v in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(v, None)

from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
history: dict[int, list[dict]] = {}

BUSINESS_CONTEXT_PATH = os.path.join(os.path.dirname(__file__), "business.md")
with open(BUSINESS_CONTEXT_PATH, "r", encoding="utf-8") as f:
    BUSINESS_CONTEXT = f.read()

STYLE_GUIDE = """Формат ответа (обязательно):
- Обычный текст, без markdown-разметки: никаких **, ##, `, |, символов
  таблиц. Заголовки — просто отдельной строкой с заглавной буквы.
- Списки — через "-" или "1.", без вложенных подпунктов.
- Пиши грамотно, ясно, короткими абзацами, деловым языком без канцелярита.
- Где это помогает понять мысль — добавь короткий конкретный пример
  (цифру, фразу, мини-сценарий).
- Без лишних эмодзи и восклицательных знаков."""

MARKETER_SYSTEM = f"""Ты — маркетолог-аналитик агентства недвижимости S House Group (Бишкек).

{BUSINESS_CONTEXT}

{STYLE_GUIDE}

Используй веб-поиск, чтобы опираться на реальные, свежие данные, и
указывай источник (сайт/дата) у каждого пункта. Веб-поиск видит обычные
сайты и статьи, но не может зайти в Instagram, Facebook или Threads —
соцсети закрыты от поисковиков, так и объясняй, если по ним нет данных.
Если ничего не нашёл или не уверен — так и скажи, не выдумывай факты и
цифры."""

CONTENT_SYSTEM = f"""Ты — контент-мейкер для Instagram агентства недвижимости S House Group
и нового проекта ЖК Dubai.

{BUSINESS_CONTEXT}

{STYLE_GUIDE}

ЖК Dubai только начал вести Instagram, сайта ещё нет — контент должен
цеплять внимание, вызывать доверие и подталкивать написать в директ."""

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 10}
TELEGRAM_MAX_LEN = 4096


async def reply_long(update: Update, text: str):
    for i in range(0, len(text), TELEGRAM_MAX_LEN):
        await update.message.reply_text(text[i:i + TELEGRAM_MAX_LEN])


def ask_claude(system_prompt: str, user_prompt: str, use_search: bool = False) -> str:
    response = claude.messages.create(
        model="claude-opus-5",
        max_tokens=2048,
        system=system_prompt,
        tools=[WEB_SEARCH_TOOL] if use_search else [],
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "\n\n".join(b.text for b in response.content if b.type == "text")
    return text or "Не получилось сформировать ответ, попробуй переформулировать."


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот на Claude для S House Group.\n"
        "Спрашивай что угодно, а ещё умею:\n\n"
        "/news — новости и тренды рынка\n"
        "/competitors — что нового у конкурентов\n"
        "/mentions <слово> — упоминания в сети\n"
        "/idea — свежие идеи для контента\n"
        "/post <тема> — готовый пост для соцсетей\n"
        "/reels <тема> — сценарий для рилса\n"
        "/reset — очистить историю диалога"
    )


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    history.pop(update.effective_user.id, None)
    await update.message.reply_text("История очищена.")


async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    history.setdefault(uid, []).append({"role": "user", "content": update.message.text})
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        resp = claude.messages.create(
            model="claude-opus-4-7", max_tokens=1024,
            system="Ты доброжелательный ассистент. Отвечай коротко и по существу на русском.",
            messages=history[uid],
        )
        text = resp.content[0].text
        history[uid].append({"role": "assistant", "content": text})
        history[uid] = history[uid][-20:]
        await update.message.reply_text(text)
    except Exception:
        log.exception("error")
        await update.message.reply_text("Ошибка. Попробуй ещё раз.")


async def news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = ask_claude(
            MARKETER_SYSTEM,
            "Найди самые свежие новости и тренды рынка недвижимости Бишкека "
            "за последние 1-2 недели: новостройки, цены, спрос, новые "
            "проекты. Сделай короткую сводку по пунктам.",
            use_search=True,
        )
        await reply_long(update, text)
    except Exception:
        log.exception("news error")
        await update.message.reply_text("Не получилось собрать новости. Попробуй ещё раз.")


async def competitors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = ask_claude(
            MARKETER_SYSTEM,
            "Найди, что сейчас публикуют и предлагают строительные компании "
            "премиум-сегмента в Бишкеке (районы выше Магистрали, ближе к "
            "горам): новые проекты, акции, цены, активность в соцсетях. "
            "Сделай короткую сводку по компаниям, которые удалось найти.",
            use_search=True,
        )
        await reply_long(update, text)
    except Exception:
        log.exception("competitors error")
        await update.message.reply_text("Не получилось собрать данные по конкурентам. Попробуй ещё раз.")


async def mentions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = " ".join(ctx.args) if ctx.args else "S House Group, ЖК Dubai"
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = ask_claude(
            MARKETER_SYSTEM,
            f"Найди в интернете свежие упоминания: {query}. "
            "Если что-то нашлось — укажи источник и краткую суть. "
            "Если ничего не нашлось — прямо скажи об этом.",
            use_search=True,
        )
        await reply_long(update, text)
    except Exception:
        log.exception("mentions error")
        await update.message.reply_text("Не получилось проверить упоминания. Попробуй ещё раз.")


async def idea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = ask_claude(
            CONTENT_SYSTEM,
            "Накидай 5 свежих идей для постов в Instagram на эту неделю "
            "для ЖК Dubai и S House Group. По каждой идее — одна строка "
            "темы и одна строка, почему она может сработать.",
        )
        await reply_long(update, text)
    except Exception:
        log.exception("idea error")
        await update.message.reply_text("Не получилось придумать идеи. Попробуй ещё раз.")


async def post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Укажи тему, например: /post скидка на квартиры с котлована")
        return
    topic = " ".join(ctx.args)
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = ask_claude(
            CONTENT_SYSTEM,
            f"Напиши готовый пост для Instagram на тему: {topic}. "
            "800-1200 знаков, цепляющее начало, призыв написать в директ "
            "в конце. Также предложи 3 варианта заголовка на выбор.",
        )
        await reply_long(update, text)
    except Exception:
        log.exception("post error")
        await update.message.reply_text("Не получилось написать пост. Попробуй ещё раз.")


async def reels(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Укажи тему, например: /reels обзор ЖК Dubai с высоты")
        return
    topic = " ".join(ctx.args)
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = ask_claude(
            CONTENT_SYSTEM,
            f"Напиши короткий сценарий рилса (30-45 секунд) на тему: {topic}. "
            "По кадрам: что происходит в кадре, что говорит/пишет текстом, "
            "какая музыка/настроение. В конце — призыв к действию.",
        )
        await reply_long(update, text)
    except Exception:
        log.exception("reels error")
        await update.message.reply_text("Не получилось написать сценарий. Попробуй ещё раз.")


def main():
    app = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("competitors", competitors))
    app.add_handler(CommandHandler("mentions", mentions))
    app.add_handler(CommandHandler("idea", idea))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("reels", reels))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    log.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
