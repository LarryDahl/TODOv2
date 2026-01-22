from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Task
from app.priority import render_title_with_priority


def _label(text: str, max_len: int = 48) -> str:
    t = text.strip()
    return t[:max_len] + ("…" if len(t) > max_len else "")


def default_kb(completed_tasks: list[dict], active_tasks: list[Task]) -> InlineKeyboardMarkup:
    """Default view: 3 completed tasks, 7 active tasks, settings/stats, edit/add buttons"""
    kb = InlineKeyboardBuilder()
    
    # 3 most recently completed tasks (reverse order: oldest first, newest last)
    # So newest is at bottom: tehty tehtävä 3, tehty tehtävä 2, tehty tehtävä 1
    # Use check mark to indicate completed tasks
    for i, comp_task in enumerate(reversed(completed_tasks), 1):
        task_text = _label(comp_task['text'], 47)
        kb.row(
            InlineKeyboardButton(
                text=f"✓ {task_text}",
                callback_data=f"completed:restore:{comp_task['id']}",
            )
        )
    
    # Separator between lists (text indicator, not a button)
    if completed_tasks and active_tasks:
        # Use a non-clickable separator - we'll add this in the message text instead
        pass
    
    # 7 next active tasks
    for task in active_tasks[:7]:
        # Render title with priority indicators (!)
        rendered_title = render_title_with_priority(task.text, task.priority)
        task_text = _label(rendered_title, 48)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"task:done:{task.id}",
            )
        )
    
    # Bottom buttons: asetukset, tilastot
    kb.row(
        InlineKeyboardButton(text="asetukset", callback_data="view:settings"),
        InlineKeyboardButton(text="tilastot", callback_data="view:stats"),
        width=2,
    )
    
    # Bottom buttons: muokkaa, lisää
    kb.row(
        InlineKeyboardButton(text="muokkaa", callback_data="view:edit"),
        InlineKeyboardButton(text="lisää", callback_data="view:add"),
        width=2,
    )
    
    return kb.as_markup()


def settings_kb() -> InlineKeyboardMarkup:
    """Settings view: nollaa, takaisin"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="nollaa", callback_data="settings:reset"))
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="view:home"))
    return kb.as_markup()


def edit_kb(tasks: list[Task]) -> InlineKeyboardMarkup:
    """Edit view: muokkaa tehtävää, deadline, schedule, poista for each task, takaisin"""
    kb = InlineKeyboardBuilder()
    
    for task in tasks:
        # Render title with priority indicators (!)
        rendered_title = render_title_with_priority(task.text, task.priority)
        task_text = _label(rendered_title, 35)
        
        # Task title button (marks as done)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"task:done:{task.id}",
            )
        )
        
        # Action buttons: muokkaa, deadline, schedule, poista
        kb.row(
            InlineKeyboardButton(
                text=f"✏️ Muokkaa",
                callback_data=f"task:edit:{task.id}",
            ),
            InlineKeyboardButton(text="⏰ Deadline", callback_data=f"task:deadline:{task.id}"),
            width=2,
        )
        kb.row(
            InlineKeyboardButton(text="🗓 Schedule", callback_data=f"task:schedule:{task.id}"),
            InlineKeyboardButton(text="🗑 Poista", callback_data=f"task:del:{task.id}"),
            width=2,
        )
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:home"))
    return kb.as_markup()


def stats_kb() -> InlineKeyboardMarkup:
    """Statistics view: analysis buttons and back"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="analyysi 1vko", callback_data="stats:7"),
        InlineKeyboardButton(text="analyysi 1kk", callback_data="stats:30"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="analyysi 3kk", callback_data="stats:90"),
        InlineKeyboardButton(text="analyysi 6kk", callback_data="stats:180"),
        width=2,
    )
    kb.row(InlineKeyboardButton(text="analyysi 1v", callback_data="stats:365"))
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="view:home"))
    return kb.as_markup()


def add_task_type_kb() -> InlineKeyboardMarkup:
    """Add task: type selection"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="deadline", callback_data="add:type:deadline"),
        InlineKeyboardButton(text="scheduled", callback_data="add:type:scheduled"),
        InlineKeyboardButton(text="regular", callback_data="add:type:regular"),
        width=3,
    )
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="view:home"))
    return kb.as_markup()


def add_task_difficulty_kb() -> InlineKeyboardMarkup:
    """Add task: difficulty selection"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="1%", callback_data="add:difficulty:1"),
        InlineKeyboardButton(text="5%", callback_data="add:difficulty:5"),
        InlineKeyboardButton(text="10%", callback_data="add:difficulty:10"),
        width=3,
    )
    kb.row(InlineKeyboardButton(text="muu %", callback_data="add:difficulty:custom"))
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="view:home"))
    return kb.as_markup()


def add_task_category_kb() -> InlineKeyboardMarkup:
    """Add task: category selection"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="liikunta", callback_data="add:category:liikunta"),
        InlineKeyboardButton(text="arki", callback_data="add:category:arki"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="opiskelu", callback_data="add:category:opiskelu"),
        InlineKeyboardButton(text="suhteet", callback_data="add:category:suhteet"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="muu", callback_data="add:category:muu"),
        InlineKeyboardButton(text="skip", callback_data="add:category:"),
        width=2,
    )
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="view:home"))
    return kb.as_markup()


def render_progress_bar(progress_percent: int) -> str:
    """Render progress bar: 10 parts, fills 10% at a time"""
    filled = progress_percent // 10
    empty = 10 - filled
    return "█" * filled + "░" * empty + f" {progress_percent}%"


def render_default_header(daily_progress: int) -> str:
    """Render default view header with progress bar"""
    progress_bar = render_progress_bar(daily_progress)
    return f"{progress_bar}\n\nTehtävälista\n\nKlikkaa tehtävää merkataksesi sen suoritetuksi.\nKlikkaa tehtyä tehtävää palauttaaksesi sen listalle."


def render_settings_header() -> str:
    return "Asetukset\n\nnollaa - Poistaa kaikki tehtävät ja tilastot"


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
    return "Kategoria\n\nValitse tehtävän kategoria tai skip jos haluat jättää tyhjäksi."


def date_picker_kb(prefix: str, include_none: bool = True) -> InlineKeyboardMarkup:
    """
    Date picker keyboard for deadline/schedule selection.
    
    Args:
        prefix: Callback data prefix (e.g., "deadline:date" or "schedule:date")
        include_none: Whether to include "No deadline" / "None" option
    """
    kb = InlineKeyboardBuilder()
    
    if include_none:
        kb.row(InlineKeyboardButton(text="Ei määräaikaa", callback_data=f"{prefix}:none"))
    
    kb.row(
        InlineKeyboardButton(text="Tänään", callback_data=f"{prefix}:0"),
        InlineKeyboardButton(text="Huomenna", callback_data=f"{prefix}:1"),
        width=2,
    )
    
    # Next 7 days
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    for i in range(2, 9):
        date = now + timedelta(days=i)
        day_name = date.strftime("%a")  # Mon, Tue, etc.
        day_num = date.day
        kb.row(InlineKeyboardButton(
            text=f"{day_name} {day_num}",
            callback_data=f"{prefix}:{i}"
        ))
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:home"))
    return kb.as_markup()


def time_picker_kb(prefix: str) -> InlineKeyboardMarkup:
    """
    Time picker keyboard with preset times and custom option.
    
    Args:
        prefix: Callback data prefix (e.g., "deadline:time" or "schedule:time")
    """
    kb = InlineKeyboardBuilder()
    
    kb.row(
        InlineKeyboardButton(text="09:00", callback_data=f"{prefix}:09:00"),
        InlineKeyboardButton(text="12:00", callback_data=f"{prefix}:12:00"),
        width=2,
    )
    kb.row(
        InlineKeyboardButton(text="18:00", callback_data=f"{prefix}:18:00"),
        InlineKeyboardButton(text="21:00", callback_data=f"{prefix}:21:00"),
        width=2,
    )
    kb.row(InlineKeyboardButton(text="Muu aika", callback_data=f"{prefix}:custom"))
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data=f"{prefix}:back"))
    return kb.as_markup()


def schedule_type_kb() -> InlineKeyboardMarkup:
    """Schedule type selection keyboard."""
    kb = InlineKeyboardBuilder()
    
    kb.row(InlineKeyboardButton(text="Ei aikataulua", callback_data="schedule:type:none"))
    kb.row(InlineKeyboardButton(text="Tietty aika", callback_data="schedule:type:at_time"))
    kb.row(InlineKeyboardButton(text="Aikaväli", callback_data="schedule:type:time_range"))
    kb.row(InlineKeyboardButton(text="Koko päivä", callback_data="schedule:type:all_day"))
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:home"))
    return kb.as_markup()
