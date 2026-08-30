"""Channel-agnostic AI core: knowledge, system prompts, and the Claude calls.

Doesn't know about Telegram (or WhatsApp, Instagram, etc.) — takes plain
message history in, returns plain text out. Any messaging channel's bot
file imports from here instead of duplicating the sales script/facts.
"""

import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(__file__)


def read_file(name: str) -> str:
    with open(os.path.join(BASE_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

BUSINESS_CONTEXT = read_file("business.md")
ZHK_DUBAI_INFO = read_file("zhk_dubai.md")
SALES_SCRIPTS = read_file("sales_scripts.md")
LEAD_MANAGER_CONTENT = read_file("lead_manager.md")

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

Факты о проекте ЖК Dubai (используй точно, не выдумывай другие цифры,
планировки, цену или сроки):

{ZHK_DUBAI_INFO}

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


def get_reply(mode: str, messages: list[dict]) -> str:
    """Internal-assistant modes (chat/marketer/content/sales) — plain text out."""
    return ask_claude(SYSTEM_PROMPTS[mode], messages, use_search=mode in SEARCH_MODES)


def split_escalation(text: str) -> tuple[str, str | None]:
    if ESCALATION_START in text and ESCALATION_END in text:
        before, _, rest = text.partition(ESCALATION_START)
        card, _, after = rest.partition(ESCALATION_END)
        return (before + after).strip(), card.strip()
    return text, None


def get_lead_reply(messages: list[dict]) -> tuple[str, str | None]:
    """Client-facing lead persona. Returns (text to show the client, escalation card or None)."""
    raw = ask_claude(SYSTEM_PROMPTS["lead"], messages)
    return split_escalation(raw)
