from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Task
from app.priority import render_title_with_priority


# UI text constants for projects
# These are user-facing labels that can be changed here centrally
UI_PROJECT_SINGULAR = "Projekti"
UI_PROJECT_PLURAL = "Projektit"
UI_ADD_PROJECT = "Lisää projekti"


def _label(text: str, max_len: int = 48) -> str:
    t = text.strip()
    return t[:max_len] + ("…" if len(t) > max_len else "")


# DEPRECATED: default_kb() removed - use build_home_keyboard() instead
# This function was replaced by build_home_keyboard() which is called via render_home_message()
# in app/handlers/common.py. All handlers should use return_to_main_menu() which calls
# render_home_message() -> build_home_keyboard().


def settings_kb(show_done: bool = True) -> InlineKeyboardMarkup:
    """
    Settings view: timezone, show done toggle, export DB, back.
    
    Args:
        show_done: Current value of show_done_in_home setting
    """
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Aseta aikavyöhyke", callback_data="settings:timezone"))
    
    # Toggle button shows current state
    toggle_text = "✅ Näytä tehdyt päänäkymässä" if show_done else "❌ Älä näytä tehtyjä päänäkymässä"
    kb.row(InlineKeyboardButton(text=toggle_text, callback_data="settings:toggle_show_done"))
    
    kb.row(InlineKeyboardButton(text="Export DB", callback_data="settings:export_db"))
    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:home"))
    return kb.as_markup()


def settings_timezone_kb() -> InlineKeyboardMarkup:
    """Timezone selection keyboard"""
    kb = InlineKeyboardBuilder()
    # Common timezones
    kb.row(InlineKeyboardButton(text="Europe/Helsinki", callback_data="settings:tz:Europe/Helsinki"))
    kb.row(InlineKeyboardButton(text="UTC", callback_data="settings:tz:UTC"))
    kb.row(InlineKeyboardButton(text="Europe/London", callback_data="settings:tz:Europe/London"))
    kb.row(InlineKeyboardButton(text="America/New_York", callback_data="settings:tz:America/New_York"))
    kb.row(InlineKeyboardButton(text="Asia/Tokyo", callback_data="settings:tz:Asia/Tokyo"))
    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:home"))
    return kb.as_markup()


def edit_kb(tasks: list[Task]) -> InlineKeyboardMarkup:
    """Edit view: list of tasks (click task to open edit menu)"""
    kb = InlineKeyboardBuilder()
    
    for task in tasks:
        # Render title with priority indicators (!)
        rendered_title = render_title_with_priority(task.text, task.priority)
        task_text = _label(rendered_title, 48)
        
        # Task title button (opens edit menu)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"task:edit_menu:{task.id}",
            )
        )
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"))
    return kb.as_markup()


def task_action_kb(task: Task) -> InlineKeyboardMarkup:
    """Action menu for a single task: muokkaa, deadline, schedule, poista"""
    kb = InlineKeyboardBuilder()
    
    # Render title with priority indicators
    rendered_title = render_title_with_priority(task.text, task.priority)
    
    # Action buttons
    kb.row(InlineKeyboardButton(text="✏️ Muokkaa", callback_data=f"task:edit:{task.id}"))
    kb.row(InlineKeyboardButton(text="⏰ Lisää deadline", callback_data=f"task:deadline:{task.id}"))
    kb.row(InlineKeyboardButton(text="🗓 Lisää schedule", callback_data=f"task:schedule:{task.id}"))
    kb.row(InlineKeyboardButton(text="🗑 Poista", callback_data=f"task:del:{task.id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"))
    
    return kb.as_markup()


def task_edit_menu_kb(task: Task) -> InlineKeyboardMarkup:
    """Edit menu for a task with quick actions"""
    kb = InlineKeyboardBuilder()
    
    # Main actions
    kb.row(InlineKeyboardButton(text="✏️ Muuta tekstiä", callback_data=f"task:edit_text:{task.id}"))
    
    # Priority actions
    kb.row(
        InlineKeyboardButton(text="⬆️ Nosta prioriteettia", callback_data=f"task:priority_up:{task.id}"),
        InlineKeyboardButton(text="⬇️ Laske prioriteettia", callback_data=f"task:priority_down:{task.id}"),
        width=2,
    )
    
    # Deadline quick actions
    has_deadline = bool(task.deadline)
    if has_deadline:
        kb.row(
            InlineKeyboardButton(text="⏰ DL +1h", callback_data=f"task:dl_plus1h:{task.id}"),
            InlineKeyboardButton(text="⏰ DL +24h", callback_data=f"task:dl_plus24h:{task.id}"),
            width=2,
        )
        kb.row(InlineKeyboardButton(text="❌ Poista DL", callback_data=f"task:dl_remove:{task.id}"))
    else:
        kb.row(
            InlineKeyboardButton(text="⏰ DL +1h", callback_data=f"task:dl_plus1h:{task.id}"),
            InlineKeyboardButton(text="⏰ DL +24h", callback_data=f"task:dl_plus24h:{task.id}"),
            width=2,
        )
    
    # Delete action
    kb.row(InlineKeyboardButton(text="🗑 Poista", callback_data=f"task:del:{task.id}"))
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"))
    
    return kb.as_markup()


def stats_menu_kb() -> InlineKeyboardMarkup:
    """
    Stats main menu: all time stats, AI analysis, reset stats.
    
    Callback data scheme:
    - view:stats -> opens this menu
    - stats:all_time -> show all time statistics
    - stats:ai -> show AI analysis options
    - stats:reset -> show reset confirmation
    - view:home -> return to home
    """
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Stats all time", callback_data="stats:all_time"))
    kb.row(InlineKeyboardButton(text="AI-analyysi", callback_data="stats:ai"))
    kb.row(InlineKeyboardButton(text="Reset stats", callback_data="stats:reset"))
    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:home"))
    return kb.as_markup()


def stats_kb() -> InlineKeyboardMarkup:
    """Statistics view: analysis buttons and back (legacy, kept for compatibility)"""
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
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="home:home"))
    return kb.as_markup()


def stats_ai_period_kb() -> InlineKeyboardMarkup:
    """AI analysis period selection"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="1 pv", callback_data="stats:ai:1"))
    kb.row(InlineKeyboardButton(text="1 vk", callback_data="stats:ai:7"))
    kb.row(InlineKeyboardButton(text="1 kk", callback_data="stats:ai:30"))
    kb.row(InlineKeyboardButton(text="1 v", callback_data="stats:ai:365"))
    kb.row(InlineKeyboardButton(text="Muu", callback_data="stats:ai:custom"))
    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:home"))
    return kb.as_markup()


def stats_reset_confirm_kb() -> InlineKeyboardMarkup:
    """Reset stats confirmation"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Varmista reset", callback_data="stats:reset_confirm"))
    kb.row(InlineKeyboardButton(text="Peru", callback_data="view:stats"))
    return kb.as_markup()


def plus_menu_kb() -> InlineKeyboardMarkup:
    """
    Plus menu: main options for adding tasks/projects or editing.
    
    Callback data scheme (documented):
    
    Main menu:
    - view:add / home:plus -> opens this plus menu
    
    Plus menu options:
    - add:task_type -> opens task type submenu (Regular/Ajastettu/Deadline)
    - add:project -> start project creation flow (same as view:add_backlog)
    - home:edit -> open edit tasks view (same as view:edit)
    - view:home -> return to home
    
    Task type submenu:
    - add:regular -> start regular task flow (direct text input, no type/difficulty/category)
    - add:scheduled -> start scheduled flow (date -> time -> text)
    - add:deadline -> start deadline flow (date -> time -> text)
    - home:plus -> back to plus menu
    
    Scheduled/Deadline flow:
    - add:scheduled:date:<offset> -> select date (0=today, 1=tomorrow, etc.)
    - add:scheduled:time:<time> -> select time (09:00, 12:00, custom, back)
    - add:deadline:date:<offset> -> select date (0=today, 1=tomorrow, etc., or none)
    - add:deadline:time:<time> -> select time (09:00, 12:00, custom, back)
    
    FSM states:
    - waiting_new_task_text -> for regular tasks (adds immediately)
    - waiting_deadline_text -> for deadline tasks (after date/time selection)
    - waiting_scheduled_text -> for scheduled tasks (after date/time selection)
    - waiting_task_deadline -> custom time input for deadline
    - waiting_task_scheduled -> custom time input for scheduled
    
    Note: "vapaa viesti = uusi tehtävä" only works when user is NOT in any FSM state.
    When in FSM state (waiting_new_task_text, waiting_deadline_text, etc.), text is treated as input.
    """
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Lisää tehtävä", callback_data="add:task_type"))
    kb.row(InlineKeyboardButton(text=UI_ADD_PROJECT, callback_data="add:project"))
    kb.row(InlineKeyboardButton(text="Muokkaa tehtäviä", callback_data="home:edit"))
    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:home"))
    return kb.as_markup()


def add_task_type_kb() -> InlineKeyboardMarkup:
    """
    Task type selection submenu (from plus menu).
    
    Callback data scheme:
    - add:task_type -> opens this menu
    - add:regular -> start regular task flow (text input, no type/difficulty/category)
    - add:scheduled -> start scheduled flow (date -> time -> text)
    - add:deadline -> start deadline flow (date -> time -> text)
    - home:plus -> back to plus menu
    - view:home -> return to home
    """
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Regular", callback_data="add:regular"))
    kb.row(InlineKeyboardButton(text="Ajastettu", callback_data="add:scheduled"))
    kb.row(InlineKeyboardButton(text="Deadline", callback_data="add:deadline"))
    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:home"))
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
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="home:home"))
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
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="home:home"))
    return kb.as_markup()


def render_progress_bar(progress_percent: int) -> str:
    """Render progress bar: 10 parts, fills 10% at a time"""
    filled = min(progress_percent // 10, 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty + f" {progress_percent}%"


# DEPRECATED: render_default_header() removed - use render_home_text() instead
# This function was replaced by render_home_text() which is called via render_home_message()
# in app/handlers/common.py. All handlers should use return_to_main_menu() which calls
# render_home_message() -> render_home_text().


def render_home_text(
    completed_count: int,
    active_count: int,
    active_steps: list[dict],
    force_refresh: bool = False
) -> str:
    """
    Render home view text with progress bar and instructions.
    
    Args:
        completed_count: Number of completed tasks
        active_count: Number of active tasks
        active_steps: List of active project steps (each has total_steps, order_index)
        force_refresh: Whether to add invisible character for force refresh
    
    Returns:
        Formatted text with progress bar and instructions
    """
    # Calculate project steps remaining
    # For each active step: remaining = total_steps - (order_index - 1)
    # order_index is 1-based, so completed = order_index - 1
    # remaining includes active (1) + pending (total_steps - order_index)
    project_steps_remaining = 0
    for step in active_steps:
        total_steps = step.get('total_steps', 0)
        order_index = step.get('order_index', 0)
        # Remaining = active (1) + pending (total_steps - order_index)
        # = 1 + (total_steps - order_index) = total_steps - order_index + 1
        # Or simpler: total_steps - completed, where completed = order_index - 1
        completed_steps = order_index - 1
        remaining = total_steps - completed_steps
        project_steps_remaining += remaining
    
    # Calculate progress: done/(done+active+project_steps_remaining)
    total_items = completed_count + active_count + project_steps_remaining
    if total_items == 0:
        progress_percent = 100
    else:
        progress_percent = int((completed_count / total_items) * 100)
    
    # Build progress bar
    progress_bar = render_progress_bar(progress_percent)
    
    # Build instructions (2-3 lines max)
    instructions = (
        "Klikkaa tehtävää = merkitse tehdyksi\n"
        "+ = lisää tehtävä\n"
        "refresh = päivitä lista"
    )
    
    # Combine
    text = f"{progress_bar}\n\n{instructions}"
    
    # Add invisible character for force refresh if needed
    if force_refresh:
        text += "\u200b"  # Zero-width space
    
    return text


def build_home_keyboard(
    completed_tasks: list[dict],
    active_tasks: list[Task],
    active_steps: list[dict]
) -> InlineKeyboardMarkup:
    """
    Build home view keyboard with reversed order (most important at bottom):
    1) Completed tasks (oldest first): 3 items
    2) Active tasks: priority order (lowest priority first, highest last)
    3) Project steps: active step per project
    4) Bottom row: [+][stats][settings][refresh]
    
    Args:
        completed_tasks: List of completed task dicts (with 'id', 'text')
        active_tasks: List of Task objects (sorted: lowest priority first, highest last)
        active_steps: List of active project step dicts
    
    Returns:
        InlineKeyboardMarkup
    """
    kb = InlineKeyboardBuilder()
    
    # 1) Completed tasks (oldest first, so newest appears at bottom)
    for comp_task in completed_tasks[:3]:
        task_text = _label(comp_task.get('text', ''), 47)
        kb.row(
            InlineKeyboardButton(
                text=f"✓ {task_text}",
                callback_data=f"completed:restore:{comp_task.get('id')}",
            )
        )
    
    # 2) Active tasks: priority order (lowest priority first, highest priority last)
    # Tasks are already sorted with lowest priority first, so render in order
    for task in active_tasks:
        rendered_title = render_title_with_priority(task.text, task.priority)
        task_text = _label(rendered_title, 48)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"t:{task.id}",
            )
        )
    
    # 3) Project steps: active step per project (appears after tasks, before UI buttons)
    # Format: "Projekti 1 · step 1" (project title and step number)
    for step in active_steps:
        project_title = step.get('project_title', 'Projekti')
        order_index = step.get('order_index', 0)
        step_id = step.get('id', 0)
        
        # Format: "Projekti 1 · step 1" (project title and step number)
        display_text = f"{project_title} · step {order_index}"
        display_text = _label(display_text, 48)
        
        kb.row(
            InlineKeyboardButton(
                text=display_text,
                callback_data=f"ps:{step_id}",
            )
        )
    
    # 4) Bottom row: [+][stats][settings][refresh] (always at the very bottom)
    kb.row(
        InlineKeyboardButton(text="+", callback_data="home:plus"),
        InlineKeyboardButton(text="stats", callback_data="view:stats"),  # Legacy, kept for compatibility
        InlineKeyboardButton(text="settings", callback_data="view:settings"),  # Legacy, kept for compatibility
        InlineKeyboardButton(text="refresh", callback_data="home:refresh"),
        width=4,
    )
    
    return kb.as_markup()


def render_settings_header(settings: dict) -> str:
    """
    Render settings header with current values.
    
    Args:
        settings: Dict with keys: timezone, show_done_in_home
    """
    timezone = settings.get('timezone', 'Europe/Helsinki')
    show_done = settings.get('show_done_in_home', True)
    
    lines = ["⚙️ Asetukset", ""]
    lines.append(f"🌍 Aikavyöhyke: {timezone}")
    lines.append(f"✅ Näytä tehdyt: {'Kyllä' if show_done else 'Ei'}")
    
    return "\n".join(lines)


def render_timezone_selection_header() -> str:
    """Header for timezone selection"""
    return "Aseta aikavyöhyke\n\nValitse aikavyöhyke:"


def render_timezone_set(timezone: str) -> str:
    """Message when timezone is set"""
    return f"✅ Aikavyöhyke asetettu: {timezone}"


def render_export_db_placeholder() -> str:
    """Placeholder message for DB export"""
    return "Export DB\n\nTulossa myöhemmin.\n\nTämä toiminto antaa sinun ladata tietokantatiedoston Telegramiin."


def render_edit_header() -> str:
    return "Muokkaa tehtäviä\n\nValitse tehtävä nähdäksesi muokkausvaihtoehdot."


def render_task_edit_menu_header(task: Task) -> str:
    """Render header for task edit menu"""
    rendered_title = render_title_with_priority(task.text, task.priority)
    deadline_info = ""
    if task.deadline:
        from app.ui import _format_task_date
        deadline_info = f"\n⏰ Määräaika: {_format_task_date(task.deadline)}"
    return f"Muokkaa tehtävää\n\n{rendered_title}{deadline_info}\n\nValitse toiminto:"


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


def render_stats_menu_header() -> str:
    """Header for stats main menu"""
    return "Tilastot\n\nValitse toiminto:"


def render_all_time_stats(stats: dict) -> str:
    """
    Render all time statistics.
    
    Args:
        stats: Dict with keys: completed_count, active_count, deleted_count, cancelled_count,
              done_today (optional), done_this_week (optional)
    """
    lines = ["📊 Tilastot - Kaikki ajat", ""]
    
    lines.append(f"✅ Tehty: {stats.get('completed_count', 0)}")
    lines.append(f"📋 Aktiivisia: {stats.get('active_count', 0)}")
    lines.append(f"❌ Poistettu: {stats.get('deleted_count', 0)}")
    
    # Cancelled count (for projects)
    cancelled = stats.get('cancelled_count', 0)
    if cancelled > 0:
        lines.append(f"🚫 Peruutettu: {cancelled}")
    
    # Today/this week stats if available
    done_today = stats.get('done_today')
    done_this_week = stats.get('done_this_week')
    
    if done_today is not None or done_this_week is not None:
        lines.append("")
        if done_today is not None:
            lines.append(f"✅ Tänään: {done_today}")
        if done_this_week is not None:
            lines.append(f"✅ Tällä viikolla: {done_this_week}")
    
    return "\n".join(lines)


def render_ai_analysis_header() -> str:
    """Header for AI analysis period selection"""
    return "AI-analyysi\n\nValitse ajanjakso analyysille:"


def render_ai_analysis_disabled() -> str:
    """Message when AI analysis is disabled"""
    return "AI-analyysi ei käytössä\n\nLisää OPENAI_API_KEY .env-tiedostoon käyttääksesi AI-analyysiä."


def render_ai_analysis_placeholder(period: str) -> str:
    """Placeholder message for AI analysis (not yet implemented)"""
    return f"AI-analyysi ei käytössä (disabled)\n\nAjanjakso: {period}\n\nAI-analyysi toteutetaan myöhemmin."


def render_reset_stats_confirm() -> str:
    """Confirmation message for resetting stats"""
    return "Resetoi tilastot?\n\nTämä poistaa kaikki tilastot ja lokit, mutta EI itse tehtäviä.\n\nHaluatko varmasti jatkaa?"


def render_plus_menu_header() -> str:
    """Header for plus menu"""
    return "Valitse toiminto:"


def render_add_type_header() -> str:
    return "Lisää tehtävä\n\nValitse tehtävätyyppi:\n• Regular - tavallinen tehtävä\n• Ajastettu - ajastettu tehtävä\n• Deadline - määräaikainen tehtävä"


def render_add_difficulty_header() -> str:
    return "Tehtävän haastavuus\n\nValitse prosentti (1% = helppo, 10% = vaikea)"


def render_add_category_header() -> str:
    return "Kategoria\n\nValitse tehtävän kategoria tai skip jos haluat jättää tyhjäksi."


def date_picker_kb(prefix: str, include_none: bool = True) -> InlineKeyboardMarkup:
    """Date picker keyboard for deadline/schedule selection."""
    from datetime import datetime, timedelta, timezone
    
    kb = InlineKeyboardBuilder()
    
    if include_none:
        kb.row(InlineKeyboardButton(text="Ei määräaikaa", callback_data=f"{prefix}:none"))
    
    kb.row(
        InlineKeyboardButton(text="Tänään", callback_data=f"{prefix}:0"),
        InlineKeyboardButton(text="Huomenna", callback_data=f"{prefix}:1"),
        width=2,
    )
    
    now = datetime.now(timezone.utc)
    for i in range(2, 9):
        date = now + timedelta(days=i)
        kb.row(InlineKeyboardButton(
            text=f"{date.strftime('%a')} {date.day}",
            callback_data=f"{prefix}:{i}"
        ))
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"))
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
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"))
    return kb.as_markup()


def _format_task_date(iso_str: str) -> str:
    """Format ISO datetime string to readable format."""
    if not iso_str:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def done_tasks_kb(tasks: list[dict], offset: int = 0) -> InlineKeyboardMarkup:
    """Done tasks view keyboard with restore buttons and pagination."""
    kb = InlineKeyboardBuilder()
    
    for task in tasks:
        task_text = _label(task.get('title', ''), 48)
        date_str = _format_task_date(task.get('updated_at', ''))
        display_text = f"✓ {task_text}" + (f" ({date_str})" if date_str else "")
        
        event_id = task.get('job_id')  # event_id from task_events
        if event_id:
            # Clicking task restores it to active
            kb.row(InlineKeyboardButton(text=display_text, callback_data=f"done:restore:{event_id}"))
        else:
            # Fallback if no event_id
            kb.row(InlineKeyboardButton(text=display_text, callback_data="noop"))
    
    if len(tasks) >= 50:
        kb.row(InlineKeyboardButton(text="📄 Näytä lisää", callback_data=f"done:page:{offset + 50}"))
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin tehtäviin", callback_data="home:home"))
    return kb.as_markup()


def deleted_tasks_kb(tasks: list[dict], offset: int = 0) -> InlineKeyboardMarkup:
    """Deleted tasks view keyboard with restore buttons and pagination."""
    kb = InlineKeyboardBuilder()
    
    for task in tasks:
        task_text = _label(task.get('title', ''), 35)
        event_id = task.get('job_id')
        date_str = _format_task_date(task.get('updated_at', ''))
        display_text = f"🗑 {task_text}" + (f" ({date_str})" if date_str else "")
        
        callback = f"deleted:restore:{event_id}" if event_id else "noop"
        kb.row(InlineKeyboardButton(text=display_text, callback_data=callback))
    
    if len(tasks) >= 50:
        kb.row(InlineKeyboardButton(text="📄 Näytä lisää", callback_data=f"deleted:page:{offset + 50}"))
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin tehtäviin", callback_data="home:home"))
    return kb.as_markup()


def suggestions_kb(suggestions: list[dict]) -> InlineKeyboardMarkup:
    """Suggestions view keyboard with accept/snooze buttons"""
    kb = InlineKeyboardBuilder()
    
    for suggestion in suggestions:
        task_text = _label(suggestion.get('text', ''), 40)
        priority = suggestion.get('priority', 0)
        
        # Render with priority indicators
        rendered_title = render_title_with_priority(task_text, priority)
        display_text = _label(rendered_title, 40)
        
        # Row: task title (non-clickable display) + action buttons
        event_id = suggestion.get('event_id')
        if event_id:
            kb.row(
                InlineKeyboardButton(
                    text=display_text,
                    callback_data="noop"  # Display only
                )
            )
            kb.row(
                InlineKeyboardButton(
                    text="✅ Lisää tehtävälistaan",
                    callback_data=f"suggestion:accept:{event_id}"
                ),
                InlineKeyboardButton(
                    text="⏸ Snooze",
                    callback_data=f"suggestion:snooze:{event_id}"
                ),
                width=2,
            )
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"))
    return kb.as_markup()


def render_suggestions_header(count: int) -> str:
    """Render suggestions view header"""
    return f"💡 Ehdotukset\n\n{count} ehdotusta {UI_PROJECT_PLURAL.lower()}sta.\n\nValitse 'Lisää tehtävälistaan' lisätäksesi tehtävän takaisin listalle."


def project_detail_kb() -> InlineKeyboardMarkup:
    """Project detail view keyboard with back button"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin listaan", callback_data="home:home"))
    return kb.as_markup()


def render_project_detail(project: dict, steps: list[dict]) -> str:
    """
    Render project detail view with all steps and their statuses.
    
    Args:
        project: Dict with keys: id, title, status, current_step_order, created_at, updated_at, completed_at
        steps: List of step dicts with keys: id, project_id, order_index, text, status, created_at, done_at
    
    Returns:
        Formatted text showing project title, steps with statuses, and progress
    """
    project_title = project.get('title', 'Unknown Project')
    
    # Count steps by status
    total_steps = len(steps)
    completed_count = sum(1 for s in steps if s.get('status') == 'completed')
    active_count = sum(1 for s in steps if s.get('status') == 'active')
    pending_count = sum(1 for s in steps if s.get('status') == 'pending')
    
    # Build header
    lines = [f"📋 {project_title}", ""]
    
    # Progress summary
    lines.append(f"Edistyminen: {completed_count}/{total_steps}")
    lines.append("")
    
    # List all steps with status
    for step in steps:
        order_index = step.get('order_index', 0)
        step_text = step.get('text', '')
        status = step.get('status', 'pending')
        
        # Format status label
        if status == 'active':
            status_label = "[ACTIVE]"
        elif status == 'completed':
            status_label = "[DONE]"
        else:  # pending
            status_label = "[PENDING]"
        
        lines.append(f"{status_label} {step_text}")
    
    return "\n".join(lines)


def render_project_completion_summary(project: dict, steps: list[dict]) -> str:
    """
    Render completion summary when a project is finished.
    
    Args:
        project: Dict with keys: id, title, status, created_at, completed_at
        steps: List of step dicts (all should be completed)
    
    Returns:
        Formatted text with project completion summary
    """
    from datetime import datetime
    
    project_title = project.get('title', 'Unknown Project')
    created_at = project.get('created_at')
    completed_at = project.get('completed_at')
    total_steps = len(steps)
    
    lines = [f"✅ {project_title} valmis", ""]
    
    # Calculate duration
    if created_at and completed_at:
        try:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            completed_dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            duration = completed_dt - created_dt
            
            # Format duration nicely
            days = duration.days
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                duration_str = f"{days} päivää"
                if hours > 0:
                    duration_str += f" {hours} tuntia"
            elif hours > 0:
                duration_str = f"{hours} tuntia"
                if minutes > 0:
                    duration_str += f" {minutes} minuuttia"
            else:
                duration_str = f"{minutes} minuuttia"
            
            lines.append(f"Kesto: {duration_str}")
        except (ValueError, AttributeError):
            # Fallback if date parsing fails
            lines.append("Kesto: laskettu")
    else:
        lines.append("Kesto: ei saatavilla")
    
    # Steps count
    lines.append(f"Askeleita: {total_steps}")
    
    # Completion timestamp (optional, as requested)
    if completed_at:
        try:
            completed_dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            # Format as readable date/time
            formatted_time = completed_dt.strftime("%Y-%m-%d %H:%M")
            lines.append(f"Valmistunut: {formatted_time}")
        except (ValueError, AttributeError):
            pass
    
    return "\n".join(lines)
