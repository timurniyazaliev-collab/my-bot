import os, logging
from datetime import time as dt_time, timezone

for v in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(v, None)

from dotenv import load_dotenv
import anthropic
from telegram import BotCommand, ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
history: dict[int, list[dict]] = {}
user_mode: dict[int, str] = {}

BASE_DIR = os.path.dirname(__file__)


def read_file(name: str) -> str:
    with open(os.path.join(BASE_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


BUSINESS_CONTEXT = read_file("business.md")
ZHK_DUBAI_INFO = read_file("zhk_dubai.md")
SALES_SCRIPTS = read_file("sales_scripts.md")

OWNER_CHAT_ID_PATH = os.path.join(BASE_DIR, "owner_chat_id.txt")


def save_owner_chat_id(chat_id: int):
    with open(OWNER_CHAT_ID_PATH, "w") as f:
        f.write(str(chat_id))


def load_owner_chat_id() -> int | None:
    try:
        with open(OWNER_CHAT_ID_PATH) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


STYLE_GUIDE = """Формат ответа (обязательно):
- Обычный текст, без markdown-разметки: никаких **, ##, `, |, символов
  таблиц. Заголовки — просто отдельной строкой с заглавной буквы.
- Списки — через "-" или "1.", без вложенных подпунктов.
- Пиши грамотно, ясно, короткими абзацами, деловым языком без канцелярита.
- Где это помогает понять мысль — добавь короткий конкретный пример
  (цифру, фразу, мини-сценарий, расчёт).
- Без лишних эмодзи и восклицательных знаков."""

ASSISTANT_ROLE = """Ты — личный ИИ-помощник Тимура: маркетолог и руководитель отдела
продаж в агентстве недвижимости S House Group (Бишкек) и его проекте
ЖК Dubai. Когда речь заходит о ЖК Dubai — это НАШ проект, ты знаешь про
него всё из фактов ниже и говоришь о нём как о своём, а не как о чужом
объекте.

Ты уверенно разбираешься в оценке недвижимости (что влияет на цену м²,
как сравнивать объекты, премиум-сегмент vs масс-маркет), и свободно
работаешь с цифрами: конверсия лидов, юнит-экономика, окупаемость,
расчёты по рассрочке и скидкам. Если тебя просят посчитать — считай
явно, показывай ход расчёта, а не только итог."""

CORE_CONTEXT = f"""{ASSISTANT_ROLE}

{BUSINESS_CONTEXT}

Факты о проекте ЖК Dubai (используй точно, не выдумывай другие цифры,
планировки, цену или сроки):

{ZHK_DUBAI_INFO}

{STYLE_GUIDE}"""

CHAT_SYSTEM = f"""{CORE_CONTEXT}

Это обычный разговорный режим: отвечай на любые вопросы — деловые и
личные, — но всегда с учётом того, что ты часть команды S House Group.
Коротко и по существу, разворачивай ответ только если вопрос сложный."""

MARKETER_SYSTEM = f"""{CORE_CONTEXT}

Используй веб-поиск, чтобы опираться на реальные, свежие данные, и
указывай источник (сайт/дата) у каждого пункта. Веб-поиск видит обычные
сайты и статьи, но не может зайти в Instagram, Facebook или Threads —
соцсети закрыты от поисковиков, так и объясняй, если по ним нет данных.
Если ничего не нашёл или не уверен — так и скажи, не выдумывай факты и
цифры."""

CONTENT_SYSTEM = f"""{CORE_CONTEXT}

Ты также контент-мейкер для Instagram S House Group и ЖК Dubai. ЖК Dubai
только начал вести Instagram, сайта ещё нет — контент должен цеплять
внимание, вызывать доверие и подталкивать написать в директ."""

SALES_SYSTEM = f"""{CORE_CONTEXT}

Скрипты продаж компании (используй как основу и адаптируй под ситуацию,
которую тебе описали — не переписывай с нуля, если не просили):

{SALES_SCRIPTS}

Помогай менеджерам по продажам: дорабатывай скрипты под конкретную
ситуацию, отвечай на возражения клиентов, объясняй условия покупки
понятным языком, которым можно сразу говорить с клиентом."""

SYSTEM_PROMPTS = {
    "chat": CHAT_SYSTEM,
    "marketer": MARKETER_SYSTEM,
    "content": CONTENT_SYSTEM,
    "sales": SALES_SYSTEM,
}
SEARCH_MODES = {"marketer"}

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 10}
TELEGRAM_MAX_LEN = 4096

BOT_COMMANDS = [
    BotCommand("news", "Новости и тренды рынка"),
    BotCommand("competitors", "Что нового у конкурентов"),
    BotCommand("mentions", "Упоминания бренда/ключевых слов"),
    BotCommand("idea", "Свежие идеи для контента"),
    BotCommand("post", "Готовый пост для соцсетей"),
    BotCommand("reels", "Сценарий для рилса"),
    BotCommand("sales", "Скрипты продаж и возражения"),
    BotCommand("reset", "Очистить историю диалога"),
]

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["/news", "/competitors"],
        ["/mentions", "/idea"],
        ["/post", "/reels"],
        ["/sales", "/reset"],
    ],
    resize_keyboard=True,
)

DAILY_DIGEST_UTC_TIME = dt_time(hour=3, minute=0, tzinfo=timezone.utc)  # 09:00 Бишкек


async def reply_long(update: Update, text: str):
    for i in range(0, len(text), TELEGRAM_MAX_LEN):
        await update.message.reply_text(text[i:i + TELEGRAM_MAX_LEN])


def ask_claude(system_prompt: str, messages: list[dict], use_search: bool = False) -> str:
    response = claude.messages.create(
        model="claude-opus-5",
        max_tokens=2048,
        system=system_prompt,
        tools=[WEB_SEARCH_TOOL] if use_search else [],
        messages=messages,
    )
    text = "\n\n".join(b.text for b in response.content if b.type == "text")
    return text or "Не получилось сформировать ответ, попробуй переформулировать."


async def run_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode: str, prompt: str, error_msg: str):
    uid = update.effective_user.id
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        history.setdefault(uid, []).append({"role": "user", "content": prompt})
        text = ask_claude(SYSTEM_PROMPTS[mode], history[uid], use_search=mode in SEARCH_MODES)
        history[uid].append({"role": "assistant", "content": text})
        history[uid] = history[uid][-20:]
        user_mode[uid] = mode
        await reply_long(update, text)
    except Exception:
        log.exception(f"{mode} command error")
        await update.message.reply_text(error_msg)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    save_owner_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "Привет! Я твой помощник на Claude — маркетолог и помощник "
        "руководителя отдела продаж S House Group.\n"
        "Спрашивай что угодно, а для остального нажимай кнопки внизу "
        "(/post, /reels и /sales ещё попросят детали — просто допиши "
        "их текстом после кнопки). После команды можно продолжать "
        "разговор обычным текстом — помню контекст, пока не позовёшь "
        "/reset или другую команду. Каждый день в 9:00 сам пришлю "
        "сводку новостей рынка.",
        reply_markup=MAIN_KEYBOARD,
    )


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    history.pop(uid, None)
    user_mode.pop(uid, None)
    await update.message.reply_text("История очищена, снова обычный режим.")


async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    mode = user_mode.get(uid, "chat")
    await run_command(update, ctx, mode, update.message.text, "Ошибка. Попробуй ещё раз.")


async def news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await run_command(
        update, ctx, "marketer",
        "Найди самые свежие новости и тренды рынка недвижимости Бишкека "
        "за последние 1-2 недели: новостройки, цены, спрос, новые "
        "проекты. Сделай короткую сводку по пунктам.",
        "Не получилось собрать новости. Попробуй ещё раз.",
    )


async def competitors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await run_command(
        update, ctx, "marketer",
        "Найди, что сейчас публикуют и предлагают строительные компании "
        "премиум-сегмента в Бишкеке (районы выше Магистрали, ближе к "
        "горам): новые проекты, акции, цены, активность в соцсетях. "
        "Сделай короткую сводку по компаниям, которые удалось найти.",
        "Не получилось собрать данные по конкурентам. Попробуй ещё раз.",
    )


async def mentions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = " ".join(ctx.args) if ctx.args else "S House Group, ЖК Dubai"
    await run_command(
        update, ctx, "marketer",
        f"Найди в интернете свежие упоминания: {query}. "
        "Если что-то нашлось — укажи источник и краткую суть. "
        "Если ничего не нашлось — прямо скажи об этом.",
        "Не получилось проверить упоминания. Попробуй ещё раз.",
    )


async def idea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await run_command(
        update, ctx, "content",
        "Накидай 5 свежих идей для постов в Instagram на эту неделю "
        "для ЖК Dubai и S House Group. По каждой идее — одна строка "
        "темы и одна строка, почему она может сработать.",
        "Не получилось придумать идеи. Попробуй ещё раз.",
    )


async def post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Укажи тему, например: /post скидка на квартиры с котлована")
        return
    topic = " ".join(ctx.args)
    await run_command(
        update, ctx, "content",
        f"Напиши готовый пост для Instagram на тему: {topic}. "
        "800-1200 знаков, цепляющее начало, призыв написать в директ "
        "в конце. Также предложи 3 варианта заголовка на выбор.",
        "Не получилось написать пост. Попробуй ещё раз.",
    )


async def reels(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Укажи тему, например: /reels обзор ЖК Dubai с высоты")
        return
    topic = " ".join(ctx.args)
    await run_command(
        update, ctx, "content",
        f"Напиши короткий сценарий рилса (30-45 секунд) на тему: {topic}. "
        "По кадрам: что происходит в кадре, что говорит/пишет текстом, "
        "какая музыка/настроение. В конце — призыв к действию.",
        "Не получилось написать сценарий. Попробуй ещё раз.",
    )


async def sales(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        prompt = (
            f"Ситуация от менеджера: {' '.join(ctx.args)}. "
            "Дай готовый ответ клиенту или конкретный совет, что "
            "сказать, опираясь на наши скрипты продаж."
        )
    else:
        prompt = (
            "Покажи кратко три базовых скрипта продаж (входящий "
            "звонок, обработка лида, исходящий звонок) — по 3-4 "
            "шага на каждый, без воды."
        )
    await run_command(update, ctx, "sales", prompt, "Не получилось собрать ответ. Попробуй ещё раз.")


async def daily_news_digest(ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = load_owner_chat_id()
    if chat_id is None:
        return
    try:
        prompt = (
            "Найди самые свежие новости и тренды рынка недвижимости "
            "Бишкека за последние сутки-двое: новостройки, цены, спрос, "
            "новые проекты. Сделай короткую сводку по пунктам."
        )
        text = ask_claude(MARKETER_SYSTEM, [{"role": "user", "content": prompt}], use_search=True)
        full_text = "Доброе утро! Сводка новостей рынка недвижимости:\n\n" + text
        for i in range(0, len(full_text), TELEGRAM_MAX_LEN):
            await ctx.bot.send_message(chat_id=chat_id, text=full_text[i:i + TELEGRAM_MAX_LEN])
    except Exception:
        log.exception("daily digest error")


async def setup_commands(app):
    await app.bot.set_my_commands(BOT_COMMANDS)
    app.job_queue.run_daily(daily_news_digest, time=DAILY_DIGEST_UTC_TIME)


def main():
    app = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).post_init(setup_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("competitors", competitors))
    app.add_handler(CommandHandler("mentions", mentions))
    app.add_handler(CommandHandler("idea", idea))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("reels", reels))
    app.add_handler(CommandHandler("sales", sales))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    log.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
