from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Task


def _label(text: str, max_len: int = 48) -> str:
    t = text.strip()
    return t[:max_len] + ("…" if len(t) > max_len else "")


def default_kb(completed_tasks: list[dict], active_tasks: list[Task]) -> InlineKeyboardMarkup:
    """Default view: 3 completed tasks, 7 active tasks, settings/stats, edit/add buttons"""
    kb = InlineKeyboardBuilder()
    
    # 3 most recently completed tasks (reverse order: oldest first, newest last)
    # So newest is at bottom: [tehty tehtävä 3] [tehty tehtävä 2] [tehty tehtävä 1]
    for i, comp_task in enumerate(reversed(completed_tasks), 1):
        task_text = _label(comp_task['text'], 48)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"completed:restore:{comp_task['id']}",
            )
        )
    
    # Aloitusviesti listojen väliin
    if completed_tasks and active_tasks:
        kb.row(
            InlineKeyboardButton(
                text="(ALOISTUSVIESTI)",
                callback_data="noop",
            )
        )
    
    # 7 next active tasks
    for task in active_tasks[:7]:
        task_text = _label(task.text, 48)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"task:done:{task.id}",
            )
        )
    
    # Bottom buttons: [asetukset][tilastot]
    kb.row(
        InlineKeyboardButton(text="[asetukset]", callback_data="view:settings"),
        InlineKeyboardButton(text="[tilastot]", callback_data="view:stats"),
        width=2,
    )
    
    # Bottom buttons: [muokkaa][lisää]
    kb.row(
        InlineKeyboardButton(text="[muokkaa]", callback_data="view:edit"),
        InlineKeyboardButton(text="[lisää]", callback_data="view:add"),
        width=2,
    )
    
    return kb.as_markup()


def settings_kb() -> InlineKeyboardMarkup:
    """Settings view: [nollaa][takaisin]"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="[nollaa]", callback_data="settings:reset"))
    kb.row(InlineKeyboardButton(text="[takaisin]", callback_data="view:home"))
    return kb.as_markup()


def edit_kb(tasks: list[Task]) -> InlineKeyboardMarkup:
    """Edit view: [muokkaa tehtävää n][poista] for each task, [takaisin]"""
    kb = InlineKeyboardBuilder()
    
    for task in tasks[:10]:  # Limit to 10 for UI
        kb.row(
            InlineKeyboardButton(
                text=f"[muokkaa {_label(task.text, 30)}]",
                callback_data=f"task:edit:{task.id}",
            ),
            InlineKeyboardButton(text="[poista]", callback_data=f"task:del:{task.id}"),
            width=2,
        )
    
    kb.row(InlineKeyboardButton(text="[takaisin]", callback_data="view:home"))
    return kb.as_markup()


def stats_kb() -> InlineKeyboardMarkup:
    """Statistics view: analysis buttons and back"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="[analyysi 1vko]", callback_data="stats:7"),
        InlineKeyboardButton(text="[analyysi 1kk]", callback_data="stats:30"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="[analyysi 3kk]", callback_data="stats:90"),
        InlineKeyboardButton(text="[analyysi 6kk]", callback_data="stats:180"),
        width=2,
    )
    kb.row(InlineKeyboardButton(text="[analyysi 1v]", callback_data="stats:365"))
    kb.row(InlineKeyboardButton(text="[takaisin]", callback_data="view:home"))
    return kb.as_markup()


def add_task_type_kb() -> InlineKeyboardMarkup:
    """Add task: type selection"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="[deadline]", callback_data="add:type:deadline"),
        InlineKeyboardButton(text="[scheduled]", callback_data="add:type:scheduled"),
        InlineKeyboardButton(text="[regular]", callback_data="add:type:regular"),
        width=3,
    )
    kb.row(InlineKeyboardButton(text="[takaisin]", callback_data="view:home"))
    return kb.as_markup()


def add_task_difficulty_kb() -> InlineKeyboardMarkup:
    """Add task: difficulty selection"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="[1%]", callback_data="add:difficulty:1"),
        InlineKeyboardButton(text="[5%]", callback_data="add:difficulty:5"),
        InlineKeyboardButton(text="[10%]", callback_data="add:difficulty:10"),
        width=3,
    )
    kb.row(InlineKeyboardButton(text="[muu %]", callback_data="add:difficulty:custom"))
    kb.row(InlineKeyboardButton(text="[takaisin]", callback_data="view:home"))
    return kb.as_markup()


def add_task_category_kb() -> InlineKeyboardMarkup:
    """Add task: category selection"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="[liikunta]", callback_data="add:category:liikunta"),
        InlineKeyboardButton(text="[arki]", callback_data="add:category:arki"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="[opiskelu]", callback_data="add:category:opiskelu"),
        InlineKeyboardButton(text="[suhteet]", callback_data="add:category:suhteet"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="[muu]", callback_data="add:category:muu"),
        InlineKeyboardButton(text="[skip]", callback_data="add:category:"),
        width=2,
    )
    kb.row(InlineKeyboardButton(text="[takaisin]", callback_data="view:home"))
    return kb.as_markup()


def render_default_header() -> str:
    return "Tehtävälista\n\nKlikkaa tehtävää merkataksesi sen suoritetuksi.\nKlikkaa tehtyä tehtävää palauttaaksesi sen listalle."


def render_settings_header() -> str:
    return "Asetukset\n\n[nollaa] - Poistaa kaikki tehtävät ja tilastot"


def render_edit_header() -> str:
    return "Muokkaa tehtäviä\n\nValitse tehtävä muokattavaksi tai poistettavaksi."


def render_stats_header(stats: dict) -> str:
    days = stats.get('days', 0)
    completed = stats.get('completed', 0)
    deleted = stats.get('deleted', 0)
    active = stats.get('active', 0)
    
    period = {
        7: "1 viikko",
        30: "1 kuukausi",
        90: "3 kuukautta",
        180: "6 kuukautta",
        365: "1 vuosi"
    }.get(days, f"{days} päivää")
    
    return f"Tilastot - {period}\n\n✅ Tehty: {completed}\n❌ Poistettu: {deleted}\n📋 Aktiivisia: {active}"


def render_add_type_header() -> str:
    return "Lisää tehtävä\n\nValitse tehtävätyyppi:\n• deadline - määräaikainen tehtävä\n• scheduled - ajastettu tehtävä\n• regular - tavallinen tehtävä"


def render_add_difficulty_header() -> str:
    return "Tehtävän haastavuus\n\nValitse prosentti (1% = helppo, 10% = vaikea)"


def render_add_category_header() -> str:
    return "Kategoria\n\nValitse tehtävän kategoria tai [skip] jos haluat jättää tyhjäksi."
