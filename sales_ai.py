"""Channel-agnostic AI core: knowledge, system prompts, and the Claude calls.

Doesn't know about Telegram (or WhatsApp, Instagram, etc.) — takes plain
message history in, returns plain text out. Any messaging channel's bot
file imports from here instead of duplicating the sales script/facts.
"""

import os
import re

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

PHOTOS_START = "###SEND_PHOTOS:"
PHOTOS_END = "###"

PHOTO_CATEGORIES_AVAILABLE = [
    "exterior",
    "plan_1k",
    "plan_2k",
    "plan_3k_86",
    "plan_3k_95",
    "plan_4k",
]

PHOTO_MARKER_GUIDE = f"""
Технический формат отправки фото (обязательно соблюдай):
Доступные категории реальных фото/планировок:
- "exterior" — рендеры внешнего вида комплекса.
- "plan_1k" — планировки 1-комнатной, 45-46 м² (пришлёт сразу оба
  варианта: этажи 3-23/юг и этажи 3-14/восток-запад).
- "plan_2k" — планировка 2-комнатной (72-74 м², этажи 3-14).
- "plan_3k_86" — планировка 3-комнатной 86-89 м² (этажи 3-22).
- "plan_3k_95" — планировка 3-комнатной 94,85 м² (только 23 этаж).
- "plan_4k" — планировка 4-комнатной (120-122 м², этажи 15-21).
Презентации в PDF пока нет — если клиент просит именно её, скажи, что
пришлёшь, как только будет готова, и передай менеджеру, метку для
этого не используй. Пентхаусов как отдельной категории фото тоже пока
нет.

Когда уместно показать фото или планировку — например, разговор дошёл
до презентации проекта, или стала понятна интересующая клиента
комнатность — напиши клиенту короткое тёплое сообщение о том, что
сейчас пришлёшь фото/планировку, и отдельным блоком в конце ответа
добавь метку {PHOTOS_START}категория{PHOTOS_END} (можно несколько
меток подряд, если уместно прислать сразу и планировку, и внешний вид)
— сами метки клиенту не отправятся, по ним система прикрепит настоящие
файлы. Отправляй только ту планировку, комнатность которой реально
интересует клиента — не вываливай все сразу. Не отправляй один и тот
же файл повторно в одном разговоре, если уже отправлял. Если фото
сейчас не нужны — не добавляй метки вообще."""

LEAD_SYSTEM = f"""{LEAD_MANAGER_CONTENT}

Факты о проекте ЖК Dubai (используй точно, не выдумывай другие цифры,
планировки, цену или сроки):

{ZHK_DUBAI_INFO}

{ESCALATION_MARKER_GUIDE}

{PHOTO_MARKER_GUIDE}"""

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


PHOTOS_PATTERN = re.compile(re.escape(PHOTOS_START) + r"(.*?)" + re.escape(PHOTOS_END))


def split_photo_request(text: str) -> tuple[str, list[str]]:
    categories = [m.strip() for m in PHOTOS_PATTERN.findall(text)]
    categories = [c for c in categories if c in PHOTO_CATEGORIES_AVAILABLE]
    cleaned = PHOTOS_PATTERN.sub("", text).strip()
    return cleaned, categories


def get_lead_reply(messages: list[dict]) -> tuple[str, str | None, list[str]]:
    """Client-facing lead persona. Returns (text to show the client, escalation card or None, photo categories to send)."""
    raw = ask_claude(SYSTEM_PROMPTS["lead"], messages)
    text_after_escalation, card = split_escalation(raw)
    client_text, photo_categories = split_photo_request(text_after_escalation)
    return client_text, card, photo_categories
