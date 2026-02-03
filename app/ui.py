# -*- coding: utf-8 -*-
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Task
from app.priority import render_title_with_priority
from app.ui_builder import ButtonSpec, build_kb


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


def settings_kb(
    show_done: bool = True,
    morning_routines_enabled: bool = False,
    evening_routines_enabled: bool = False,
) -> InlineKeyboardMarkup:
    """
    Settings view: timezone, show done, morning/evening routines toggles, export DB, back.

    Args:
        show_done: Current value of show_done_in_home setting
        morning_routines_enabled: Current value of morning_routines_enabled
        evening_routines_enabled: Current value of evening_routines_enabled
    """
    from app.callbacks import (
        SETTINGS_TOGGLE_MORNING_ROUTINES,
        SETTINGS_TOGGLE_EVENING_ROUTINES,
    )
    toggle_text = "✅ Näytä tehdyt päänäkymässä" if show_done else "❌ Älä näytä tehtyjä päänäkymässä"
    morning_text = "✅ Aamurutiinit päällä" if morning_routines_enabled else "❌ Aamurutiinit pois"
    evening_text = "✅ Iltarutiinit päällä" if evening_routines_enabled else "❌ Iltarutiinit pois"
    return build_kb([
        [ButtonSpec("Aseta aikavyöhyke", "settings:timezone")],
        [ButtonSpec(toggle_text, "settings:toggle_show_done")],
        [ButtonSpec(morning_text, SETTINGS_TOGGLE_MORNING_ROUTINES)],
        [ButtonSpec(evening_text, SETTINGS_TOGGLE_EVENING_ROUTINES)],
        [ButtonSpec("Export DB", "settings:export_db")],
        [ButtonSpec("Takaisin", "home:home")],
    ])


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
    return build_kb([
        [ButtonSpec("Stats all time", "stats:all_time")],
        [ButtonSpec("AI-analyysi", "stats:ai")],
        [ButtonSpec("Reset stats", "stats:reset")],
        [ButtonSpec("Takaisin", "home:home")],
    ])


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
    """
    Render progress bar: 10 parts, fills 10% at a time.
    Progress percent can be > 100%, but bar is capped at 100%.
    """
    # Bar is always max 100%, but show actual percentage in text
    bar_percent = min(progress_percent, 100)
    filled = min(bar_percent // 10, 10)
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
    # Calculate progress: 1 completed task = 10%
    # Progress can exceed 100%, but bar is capped at 100%
    progress_percent = completed_count * 10
    
    # Build progress bar
    progress_bar = render_progress_bar(progress_percent)
    
    # Build instructions (UTF-8, emojis for nav)
    instructions = (
        "Uusi viesti = uusi tehtävä\n"
        "! viestin lopussa = +1 prioriteetti\n"
        "Klikkaa tehtävää = valmis\n"
        "➕ lisää/muokkaa\n"
        "📊 tilastot\n"
        "⚙️ asetukset\n"
        "📋 projektit\n"
        "🔄 päivitä lista\n"
        "✅ viimeisin tehty tehtävä\n"
        "▶ aktiivinen tehtävä\n"
        "💡 ehdotukset"
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
    active_steps: list[dict],
) -> InlineKeyboardMarkup:
    """Legacy: done (1) → active (▶) → Projektit + nav. Prefer build_main_keyboard_6_3 for main view."""
    kb = InlineKeyboardBuilder()
    # 1) Done tasks (1 most recent)
    for comp_task in completed_tasks[:1]:
        task_text = _label(comp_task.get("text", ""), 47)
        kb.row(InlineKeyboardButton(text=f"✓ {task_text}", callback_data=f"completed:restore:{comp_task.get('id')}"))
    # 2) Active tasks (▶ prefix)
    for task in active_tasks:
        rendered_title = render_title_with_priority(task.text, task.priority)
        kb.row(InlineKeyboardButton(text=f"▶ {_label(rendered_title, 46)}", callback_data=f"t:{task.id}"))
    kb.row(InlineKeyboardButton(text="📋 Projektit", callback_data="view:projects"))
    kb.row(
        InlineKeyboardButton(text="➕", callback_data="home:plus"),
        InlineKeyboardButton(text="📊", callback_data="view:stats"),
        InlineKeyboardButton(text="⚙️", callback_data="view:settings"),
        InlineKeyboardButton(text="📋", callback_data="view:projects"),
        InlineKeyboardButton(text="🔄", callback_data="home:refresh"),
        width=5,
    )
    return kb.as_markup()


def build_main_keyboard_6_3(
    active_tasks: list[Task],
    suggestion_tasks: list[Task | None],
    completed_tasks: list[dict],
) -> InlineKeyboardMarkup:
    """
    Default view: done (1) → active (▶) → suggestions (💡) → one menu row. Total 1 + 9 task rows.
    One button per task row. Menu: + | 📊 | ⚙️ | 🔄 | 📋
    """
    rows: list[list[ButtonSpec]] = []
    # 1) Done tasks (1 most recent)
    for comp_task in completed_tasks[:1]:
        task_text = _label(comp_task.get("text", ""), 47)
        rows.append([ButtonSpec(f"✓ {task_text}", f"completed:restore:{comp_task.get('id')}")])
    # 2) Active tasks (▶ prefix; click = mark done), max 9
    for task in active_tasks[:9]:
        rendered_title = render_title_with_priority(task.text, task.priority)
        rows.append([ButtonSpec(f"▶ {_label(rendered_title, 46)}", f"t:{task.id}")])
    # 3) Suggestion rows (💡 prefix; click = set active); no placeholder for empty slots
    for task in suggestion_tasks:
        if task is None:
            continue
        rendered_title = render_title_with_priority(task.text, task.priority)
        rows.append([ButtonSpec(f"💡 {_label(rendered_title, 46)}", f"sug:active:{task.id}")])
    # 4) One menu row: + | stats | settings | projektit | refresh
    rows.append([
        ButtonSpec("➕", "home:plus"),
        ButtonSpec("📊", "view:stats"),
        ButtonSpec("⚙️", "view:settings"),
        ButtonSpec("📋", "view:projects"),
        ButtonSpec("🔄", "home:refresh"),
    ])
    row_widths = [None] * (len(rows) - 1) + [5]
    return build_kb(rows, row_widths)


def render_active_card_text(task: Task) -> str:
    """Text for the separate Active task card message."""
    title = render_title_with_priority(task.text, task.priority)
    return f"▶ Aktiivinen tehtävä\n\n{_label(title, 200)}"


def active_card_kb(task: Task) -> InlineKeyboardMarkup:
    """Single button: Mark done (moves to done list, clears active)."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✓ Merkitse tehdyksi", callback_data=f"t:{task.id}"))
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


def render_ai_analysis_result(period: str, analysis_text: str) -> str:
    """Header + AI analysis result for the chosen period"""
    return f"🤖 AI-analyysi — {period}\n\n{analysis_text}"


def render_ai_analysis_error() -> str:
    """Shown when AI analysis fails; instructs user to use back button."""
    return "Analyysi epäonnistui. Käytä Takaisin-nappia palataksesi tilastoihin."


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


def render_projects_list_header() -> str:
    """Header for projects list (päänäkymä > projektit)"""
    return (
        "📋 Projektit\n\n"
        "Projekti on tehtäväkokoelma: lista askeleita, jotka merkitään tehdyiksi yksi kerrallaan.\n\n"
        "Valitse projekti nähdäksesi askeleet tai tee uusi projekti."
    )


def projects_list_kb(projects: list[dict]) -> InlineKeyboardMarkup:
    """Projects list: Tee projekti, then project buttons, then Asetukset + Takaisin"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ " + UI_ADD_PROJECT, callback_data="add:project"))
    for project in projects:
        title = project.get("title", "Untitled")
        status = project.get("status", "active")
        if status == "completed":
            status_icon = "✅"
        elif status == "cancelled":
            status_icon = "❌"
        else:
            status_icon = "📋"
        project_text = f"{status_icon} {_label(title, 45)}"
        project_id = project.get("id", 0)
        kb.row(
            InlineKeyboardButton(
                text=project_text,
                callback_data=f"view:project:{project_id}",
            )
        )
    kb.row(
        InlineKeyboardButton(text="⚙️ Asetukset", callback_data="edit:projects"),
        InlineKeyboardButton(text="⬅️ Takaisin", callback_data="home:home"),
        width=2,
    )
    return kb.as_markup()


def _project_completion_ranks(steps: list[dict]) -> dict[int, int]:
    """Return step_id -> completion_rank (1-based) for completed steps, by done_at order."""
    completed = [(s.get("id"), s.get("done_at") or "") for s in steps if s.get("status") == "completed"]
    completed.sort(key=lambda x: x[1])
    return {step_id: rank for rank, (step_id, _) in enumerate(completed, start=1)}


def project_detail_view_kb(project: dict, steps: list[dict]) -> InlineKeyboardMarkup:
    """Project detail view: each step as button (toggle done), back to project list.
    Undone steps: plain text. Done steps: ✅ and completion order number."""
    kb = InlineKeyboardBuilder()
    ranks = _project_completion_ranks(steps)
    for step in steps:
        step_id = step.get("id", 0)
        step_text = step.get("text", "")
        status = step.get("status", "pending")
        if status == "completed":
            rank = ranks.get(step_id, 0)
            step_display = f"✅ {rank}. {_label(step_text, 40)}"
        else:
            step_display = _label(step_text, 40)
        kb.row(
            InlineKeyboardButton(
                text=step_display,
                callback_data=f"proj:step:toggle:{step_id}",
            )
        )
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:projects"))
    return kb.as_markup()


def project_detail_kb() -> InlineKeyboardMarkup:
    """Project detail view keyboard with back button (legacy)"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin listaan", callback_data="view:projects"))
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
    
    # Completion order for done steps (by done_at)
    ranks = _project_completion_ranks(steps)
    # List all steps: undone = plain text, done = ✅ and completion number
    for step in steps:
        step_text = step.get('text', '')
        status = step.get('status', 'pending')
        step_id = step.get('id', 0)
        if status == 'completed':
            rank = ranks.get(step_id, 0)
            lines.append(f"✅ {rank}. {step_text}")
        else:
            lines.append(step_text)
    
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


def render_projects_edit_header() -> str:
    return "Muokkaa projekteja\n\nValitse projekti muokataksesi sen askelmia."


def projects_edit_kb(projects: list[dict]) -> InlineKeyboardMarkup:
    """Edit view: list of projects (click project to edit steps)"""
    kb = InlineKeyboardBuilder()
    
    for project in projects:
        title = project.get('title', 'Untitled')
        status = project.get('status', 'active')
        
        # Format status indicator
        if status == 'completed':
            status_icon = "✅"
        elif status == 'cancelled':
            status_icon = "❌"
        else:
            status_icon = "📋"
        
        project_text = f"{status_icon} {_label(title, 45)}"
        project_id = project.get('id', 0)
        
        kb.row(
            InlineKeyboardButton(
                text=project_text,
                callback_data=f"edit:project:{project_id}",
            )
        )
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:projects"))
    return kb.as_markup()


def project_steps_edit_kb(project: dict, steps: list[dict]) -> InlineKeyboardMarkup:
    """Edit view: list of project steps with edit/delete/reorder options.
    Undone steps: plain text. Done steps: ✅ and completion order number."""
    kb = InlineKeyboardBuilder()
    
    project_id = project.get('id', 0)
    ranks = _project_completion_ranks(steps)
    
    for step in steps:
        step_id = step.get('id', 0)
        step_text = step.get('text', '')
        status = step.get('status', 'pending')
        if status == 'completed':
            rank = ranks.get(step_id, 0)
            step_display = f"✅ {rank}. {_label(step_text, 40)}"
        else:
            step_display = _label(step_text, 40)
        kb.row(
            InlineKeyboardButton(
                text=step_display,
                callback_data=f"edit:step:menu:{step_id}",
            )
        )
    
    # Add step button
    kb.row(InlineKeyboardButton(text="➕ Lisää tehtävä", callback_data=f"edit:step:add:{project_id}"))
    
    # Reorder button
    kb.row(InlineKeyboardButton(text="🔄 Järjestä uudelleen", callback_data=f"edit:step:reorder:{project_id}"))
    
    # Rewrite project button
    kb.row(InlineKeyboardButton(text="✏️ Uudelleenkirjoita projekti", callback_data=f"edit:project:rewrite:{project_id}"))
    
    # Delete project
    kb.row(InlineKeyboardButton(text="🗑 Poista projekti", callback_data=f"edit:project:delete:{project_id}"))
    
    # Back button
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="edit:projects"))
    
    return kb.as_markup()


def render_project_steps_edit_header(project: dict, steps: list[dict]) -> str:
    """Render header for project steps edit view"""
    project_title = project.get('title', 'Unknown Project')
    total_steps = len(steps)
    completed_count = sum(1 for s in steps if s.get('status') == 'completed')

    lines = [f"📋 {project_title}", ""]
    lines.append(f"Askeleita: {completed_count}/{total_steps} valmiina")
    lines.append("")
    lines.append("Klikkaa askelta muokataksesi sitä.")

    return "\n".join(lines)


def render_routine_list_edit_header(routine_type: str) -> str:
    """Header for routine list edit view (morning/evening)."""
    label = "Aamurutiini" if routine_type == "morning" else "Iltarutiini"
    return f"{label} – tehtävät\n\nValitse tehtävä muokataksesi tai lisää uusi."


def routine_list_edit_kb(routine_type: str, tasks: list[dict]) -> InlineKeyboardMarkup:
    """Edit view: list of routine tasks (click to edit), add, back."""
    kb = InlineKeyboardBuilder()
    for task in tasks:
        task_text = _label(task.get("text", ""), 48)
        task_id = task.get("id", 0)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"routine:edit_task:{routine_type}:{task_id}",
            )
        )
    kb.row(InlineKeyboardButton(text="➕ Lisää tehtävä", callback_data=f"routine:add:{routine_type}"))
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="settings:routines:edit_menu"))
    return kb.as_markup()


def render_routine_active_header(routine_type: str, all_done: bool) -> str:
    """Header for active routine view (morning/evening). all_done=True when every task is done today."""
    label = "Aamurutiini" if routine_type == "morning" else "Iltarutiini"
    if all_done:
        return f"{label}\n\n✅ Kaikki tehty! Klikkaa 'Kuittaa tehdyksi' palataksesi normaaliruutuun."
    return f"{label}\n\nMerkitse tehtävät tehdyiksi tai kuittaa rutiini lopuksi."


def routine_active_kb(
    routine_type: str,
    tasks: list[dict],
    completed: set[int],
    all_done: bool,
) -> InlineKeyboardMarkup:
    """Active routine view: one button per task (toggle done), optionally 'Kuittaa tehdyksi', Muokkaa listaa."""
    kb = InlineKeyboardBuilder()
    for task in tasks:
        task_id = task.get("id", 0)
        task_text = _label(task.get("text", ""), 48)
        is_done = task_id in completed
        prefix = "✅ " if is_done else "☐ "
        kb.row(
            InlineKeyboardButton(
                text=f"{prefix}{task_text}",
                callback_data=f"routine:toggle:{routine_type}:{task_id}",
            )
        )
    if all_done:
        kb.row(
            InlineKeyboardButton(
                text="Kuittaa tehdyksi",
                callback_data=f"routine:quitted:{routine_type}",
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="✏️ Muokkaa listaa",
            callback_data=f"routine:edit_list:{routine_type}",
        )
    )
    return kb.as_markup()


def step_edit_menu_kb(step: dict, project_id: int) -> InlineKeyboardMarkup:
    """Edit menu for a single step"""
    kb = InlineKeyboardBuilder()
    
    step_id = step.get('id', 0)
    status = step.get('status', 'pending')
    
    # Edit text
    kb.row(InlineKeyboardButton(text="✏️ Muuta tekstiä", callback_data=f"edit:step:text:{step_id}"))
    
    # Status actions
    if status == 'pending':
        kb.row(InlineKeyboardButton(text="▶️ Aktivoi", callback_data=f"edit:step:activate:{step_id}"))
    elif status == 'active':
        kb.row(InlineKeyboardButton(text="✅ Merkitse tehdyksi", callback_data=f"edit:step:complete:{step_id}"))
        kb.row(InlineKeyboardButton(text="⏸️ Palauta odottamaan", callback_data=f"edit:step:deactivate:{step_id}"))
    elif status == 'completed':
        kb.row(InlineKeyboardButton(text="⏸️ Palauta odottamaan", callback_data=f"edit:step:deactivate:{step_id}"))
    
    # Move up/down
    kb.row(
        InlineKeyboardButton(text="⬆️ Siirrä ylös", callback_data=f"edit:step:move_up:{step_id}"),
        InlineKeyboardButton(text="⬇️ Siirrä alas", callback_data=f"edit:step:move_down:{step_id}"),
        width=2,
    )
    
    # Delete step (poista tehtävä)
    kb.row(InlineKeyboardButton(text="🗑 Poista tehtävä", callback_data=f"edit:step:delete:{step_id}"))
    
    # Back to steps list
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data=f"edit:project:{project_id}"))
    
    return kb.as_markup()
