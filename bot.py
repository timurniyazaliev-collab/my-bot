import asyncio
import os, logging
from datetime import time as dt_time, timezone, timedelta

for v in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(v, None)

from dotenv import load_dotenv
import anthropic
from telegram import BotCommand, BotCommandScopeChat, ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import wb_report_file
import wb_sync

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
history: dict[int, list[dict]] = {}
last_wb_report: dict[int, dict] = {}
user_mode: dict[int, str] = {}

BASE_DIR = os.path.dirname(__file__)


def read_file(name: str) -> str:
    with open(os.path.join(BASE_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


BUSINESS_CONTEXT = read_file("business.md")
ZHK_DUBAI_INFO = read_file("zhk_dubai.md")
SALES_SCRIPTS = read_file("sales_scripts.md")
LEAD_MANAGER_CONTENT = read_file("lead_manager.md")

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


def is_owner_chat(chat_id: int) -> bool:
    owner_id = load_owner_chat_id()
    return owner_id is not None and chat_id == owner_id


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

ESCALATION_START = "###ESCALATION_START###"
ESCALATION_END = "###ESCALATION_END###"

ESCALATION_MARKER_GUIDE = f"""
Технический формат передачи лида (обязательно соблюдай):
Когда по правилам эскалации нужно передать лида живому менеджеру,
сначала напиши клиенту короткое тёплое сообщение о том, что подключаешь
коллегу — без карточки лида в этом сообщении. Затем отдельным блоком в
самом конце ответа выведи карточку лида строго между метками
{ESCALATION_START} и {ESCALATION_END} — этот блок клиенту не отправится,
он уходит менеджеру напрямую. Если эскалация не нужна — не добавляй эти
метки вообще."""

LEAD_SYSTEM = f"""{LEAD_MANAGER_CONTENT}

{ESCALATION_MARKER_GUIDE}"""

LEAD_GREETING = (
    "Здравствуйте! Это ИИ-помощник отдела продаж ЖК Dubai (S House "
    "Group). Подскажите, пожалуйста, удобно ли вам сейчас немного "
    "пообщаться, или лучше вернусь чуть позже?"
)

SYSTEM_PROMPTS = {
    "chat": CHAT_SYSTEM,
    "marketer": MARKETER_SYSTEM,
    "content": CONTENT_SYSTEM,
    "sales": SALES_SYSTEM,
    "lead": LEAD_SYSTEM,
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
    BotCommand("wb_preview", "Черновик сводного отчёта WB за неделю (только в чат)"),
    BotCommand("wb_apply", "Записать в таблицу цифры из последнего файла WB"),
    BotCommand("wb_sync", "Синхронизировать отчёты WB с Google Таблицами"),
    BotCommand("reset", "Очистить историю диалога"),
]

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["/news", "/competitors"],
        ["/mentions", "/idea"],
        ["/post", "/reels"],
        ["/sales", "/reset"],
        ["/wb_preview", "/wb_apply"],
    ],
    resize_keyboard=True,
)

DAILY_DIGEST_UTC_TIME = dt_time(hour=3, minute=0, tzinfo=timezone.utc)  # 09:00 Бишкек

LEAD_NUDGE_DELAY = timedelta(hours=24)
LEAD_SILENCE_ESCALATE_DELAY = timedelta(days=3)


def split_escalation(text: str) -> tuple[str, str | None]:
    if ESCALATION_START in text and ESCALATION_END in text:
        before, _, rest = text.partition(ESCALATION_START)
        card, _, after = rest.partition(ESCALATION_END)
        return (before + after).strip(), card.strip()
    return text, None


def _lead_job_name(kind: str, uid: int) -> str:
    return f"lead_{kind}_{uid}"


def cancel_lead_followups(ctx: ContextTypes.DEFAULT_TYPE, uid: int):
    for kind in ("nudge", "silence"):
        for job in ctx.job_queue.get_jobs_by_name(_lead_job_name(kind, uid)):
            job.schedule_removal()


def schedule_lead_followups(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, uid: int):
    cancel_lead_followups(ctx, uid)
    ctx.job_queue.run_once(
        lead_nudge_job, LEAD_NUDGE_DELAY, chat_id=chat_id, name=_lead_job_name("nudge", uid), data={"uid": uid}
    )
    ctx.job_queue.run_once(
        lead_silence_escalate_job,
        LEAD_SILENCE_ESCALATE_DELAY,
        chat_id=chat_id,
        name=_lead_job_name("silence", uid),
        data={"uid": uid},
    )


async def lead_nudge_job(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(
        chat_id=ctx.job.chat_id,
        text="Добрый день! Остались ли у вас вопросы по ЖК Dubai, или что-то заинтересовало в презентации?",
    )


async def lead_silence_escalate_job(ctx: ContextTypes.DEFAULT_TYPE):
    owner_id = load_owner_chat_id()
    if owner_id is None:
        return
    uid = ctx.job.data["uid"]
    await ctx.bot.send_message(
        chat_id=owner_id,
        text=f"Лид id{uid} не отвечает уже 3 дня после последнего контакта — стоит написать напрямую.",
    )


async def forward_lead_card(ctx: ContextTypes.DEFAULT_TYPE, update: Update, card: str):
    owner_id = load_owner_chat_id()
    if owner_id is None:
        return
    user = update.effective_user
    contact = f"@{user.username}" if user.username else f"id{user.id}"
    link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    header = f"Новый лид от {user.full_name} ({contact})\n{link}\n\n"
    await ctx.bot.send_message(chat_id=owner_id, text=header + card)


async def reply_long(update: Update, text: str):
    for i in range(0, len(text), TELEGRAM_MAX_LEN):
        await update.message.reply_text(text[i:i + TELEGRAM_MAX_LEN])


async def reply_table(update: Update, table: str):
    chunk_size = TELEGRAM_MAX_LEN - 8  # leave room for the ```\n ... \n``` fence
    for i in range(0, len(table), chunk_size):
        await update.message.reply_text(f"```\n{table[i:i + chunk_size]}\n```", parse_mode="Markdown")


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


async def handle_lead_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        history.setdefault(uid, []).append({"role": "user", "content": update.message.text})
        raw = ask_claude(SYSTEM_PROMPTS["lead"], history[uid])
        history[uid].append({"role": "assistant", "content": raw})
        history[uid] = history[uid][-30:]
        client_text, card = split_escalation(raw)
        if client_text:
            await reply_long(update, client_text)
        if card:
            await forward_lead_card(ctx, update, card)
            cancel_lead_followups(ctx, uid)
        else:
            schedule_lead_followups(ctx, chat_id, uid)
    except Exception:
        log.exception("lead chat error")
        await update.message.reply_text("Секунду, что-то пошло не так — уточню и вернусь с ответом.")


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if load_owner_chat_id() is None:
        save_owner_chat_id(chat_id)

    if is_owner_chat(chat_id):
        await ctx.bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeChat(chat_id=chat_id))
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
        return

    uid = update.effective_user.id
    user_mode[uid] = "lead"
    await update.message.reply_text(LEAD_GREETING)
    schedule_lead_followups(ctx, chat_id, uid)


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    history.pop(uid, None)
    if is_owner_chat(chat_id):
        user_mode.pop(uid, None)
        await update.message.reply_text("История очищена, снова обычный режим.")
        return
    user_mode[uid] = "lead"
    cancel_lead_followups(ctx, uid)
    await update.message.reply_text("История очищена, начнём заново.")


async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if is_owner_chat(chat_id):
        uid = update.effective_user.id
        mode = user_mode.get(uid, "chat")
        await run_command(update, ctx, mode, update.message.text, "Ошибка. Попробуй ещё раз.")
        return
    await handle_lead_message(update, ctx)


def owner_only(handler):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_owner_chat(update.effective_chat.id):
            await handle_lead_message(update, ctx)
            return
        await handler(update, ctx)
    return wrapper


@owner_only
async def news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await run_command(
        update, ctx, "marketer",
        "Найди самые свежие новости и тренды рынка недвижимости Бишкека "
        "за последние 1-2 недели: новостройки, цены, спрос, новые "
        "проекты. Сделай короткую сводку по пунктам.",
        "Не получилось собрать новости. Попробуй ещё раз.",
    )


@owner_only
async def competitors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await run_command(
        update, ctx, "marketer",
        "Найди, что сейчас публикуют и предлагают строительные компании "
        "премиум-сегмента в Бишкеке (районы выше Магистрали, ближе к "
        "горам): новые проекты, акции, цены, активность в соцсетях. "
        "Сделай короткую сводку по компаниям, которые удалось найти.",
        "Не получилось собрать данные по конкурентам. Попробуй ещё раз.",
    )


@owner_only
async def mentions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = " ".join(ctx.args) if ctx.args else "S House Group, ЖК Dubai"
    await run_command(
        update, ctx, "marketer",
        f"Найди в интернете свежие упоминания: {query}. "
        "Если что-то нашлось — укажи источник и краткую суть. "
        "Если ничего не нашлось — прямо скажи об этом.",
        "Не получилось проверить упоминания. Попробуй ещё раз.",
    )


@owner_only
async def idea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await run_command(
        update, ctx, "content",
        "Накидай 5 свежих идей для постов в Instagram на эту неделю "
        "для ЖК Dubai и S House Group. По каждой идее — одна строка "
        "темы и одна строка, почему она может сработать.",
        "Не получилось придумать идеи. Попробуй ещё раз.",
    )


@owner_only
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


@owner_only
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


@owner_only
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


@owner_only
async def wb_sync_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Запись в таблицу пока отключена — она затирала нулями реальные цифры, "
        "когда не могла получить данные от WB. Используй /wb_preview, чтобы свериться, "
        "прежде чем включим запись обратно."
    )


@owner_only
async def wb_preview_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("Считаю черновик по неделе, это может занять минуту...")
    try:
        table, note = await asyncio.to_thread(wb_sync.preview_week)
        await reply_table(update, table)
        await update.message.reply_text(note)
    except KeyError as e:
        await update.message.reply_text(
            f"Не настроена переменная окружения {e} в .env на сервере. "
            "Нужны WB_API_TOKEN, GOOGLE_SHEET_ID и файл google_service_account.json."
        )
    except Exception:
        log.exception("wb_preview command error")
        await update.message.reply_text("Не получилось посчитать черновик. Попробуй ещё раз позже.")


async def wb_report_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner_chat(update.effective_chat.id):
        return
    doc = update.message.document
    if not doc.file_name.lower().endswith(".xlsx"):
        return
    uid = update.effective_user.id
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        tg_file = await ctx.bot.get_file(doc.file_id)
        path = os.path.join(BASE_DIR, f"wb_report_{uid}.xlsx")
        await tg_file.download_to_drive(path)
        by_date = await asyncio.to_thread(wb_report_file.parse_summary_report, path)
        last_wb_report[uid] = by_date
        table, note = wb_report_file.format_preview(by_date)
        if table:
            await reply_table(update, table)
        await update.message.reply_text(note)
    except Exception:
        log.exception("wb_report_document error")
        await update.message.reply_text("Не получилось разобрать файл. Проверь, что это выгрузка «Сводного по продавцу», и попробуй ещё раз.")


@owner_only
async def wb_apply_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    by_date = last_wb_report.get(uid)
    if not by_date:
        await update.message.reply_text("Сначала пришли файл выгрузки «Сводного по продавцу» (.xlsx).")
        return
    await update.message.reply_text("Записываю в таблицу...")
    try:
        summary = await asyncio.to_thread(wb_sync.apply_report_file, by_date)
        await update.message.reply_text("Готово:\n\n" + summary)
    except KeyError as e:
        await update.message.reply_text(
            f"Не настроена переменная окружения {e} в .env на сервере. "
            "Нужны GOOGLE_SHEET_ID и файл google_service_account.json."
        )
    except Exception:
        log.exception("wb_apply command error")
        await update.message.reply_text("Не получилось записать в таблицу. Попробуй ещё раз позже.")


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
    await app.bot.set_my_commands([])  # клиентам не показываем внутренние команды
    owner_id = load_owner_chat_id()
    if owner_id is not None:
        await app.bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeChat(chat_id=owner_id))
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
    app.add_handler(CommandHandler("wb_sync", wb_sync_cmd))
    app.add_handler(CommandHandler("wb_preview", wb_preview_cmd))
    app.add_handler(CommandHandler("wb_apply", wb_apply_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, wb_report_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    log.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
