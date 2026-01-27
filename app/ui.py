from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Task
from app.priority import render_title_with_priority


def _label(text: str, max_len: int = 48) -> str:
    t = text.strip()
    return t[:max_len] + ("…" if len(t) > max_len else "")


def default_kb(completed_tasks: list[dict], active_tasks: list[Task], active_steps: list[dict] | None = None) -> InlineKeyboardMarkup:
    """Default view: 3 completed tasks, 7 active tasks, active project steps, settings/stats, edit/add buttons"""
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
    if completed_tasks and (active_tasks or (active_steps and len(active_steps) > 0)):
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
    
    # Active project steps (append after tasks)
    if active_steps:
        for step in active_steps:
            project_title = step.get('project_title', '')
            step_text = step.get('text', '')
            order_index = step.get('order_index', 0)
            total_steps = step.get('total_steps', 0)
            step_id = step.get('id', 0)
            project_id = step.get('project_id', 0)
            
            # Format: "[PRJ] <Project title>: <step text> [i/N]"
            display_text = f"[PRJ] {project_title}: {step_text} [{order_index}/{total_steps}]"
            display_text = _label(display_text, 48)
            
            # Two buttons: step action and project view
            kb.row(
                InlineKeyboardButton(
                    text=display_text,
                    callback_data=f"ps:{step_id}",
                ),
                InlineKeyboardButton(
                    text="📋",
                    callback_data=f"p:{project_id}",
                ),
                width=2,
            )
    
    # Bottom buttons: lisää, backlog, tehty, poista, muokkaa
    kb.row(
        InlineKeyboardButton(text="lisää", callback_data="view:add"),
        InlineKeyboardButton(text="backlog", callback_data="view:add_backlog"),
        InlineKeyboardButton(text="tehty", callback_data="view:done"),
        InlineKeyboardButton(text="poista", callback_data="view:deleted"),
        width=4,
    )
    kb.row(
        InlineKeyboardButton(text="muokkaa", callback_data="view:edit"),
    )
    
    # Bottom buttons: asetukset, tilastot, päivitä
    kb.row(
        InlineKeyboardButton(text="asetukset", callback_data="view:settings"),
        InlineKeyboardButton(text="tilastot", callback_data="view:stats"),
        InlineKeyboardButton(text="päivitä", callback_data="view:refresh"),
        width=3,
    )
    
    # Suggestions button
    kb.row(InlineKeyboardButton(text="Ehdotukset", callback_data="view:suggestions"))
    
    return kb.as_markup()


def settings_kb() -> InlineKeyboardMarkup:
    """Settings view: nollaa, takaisin"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="nollaa", callback_data="settings:reset"))
    kb.row(InlineKeyboardButton(text="takaisin", callback_data="view:home"))
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
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:home"))
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
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:edit"))
    
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
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:edit"))
    
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
    filled = min(progress_percent // 10, 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty + f" {progress_percent}%"


def render_default_header(daily_progress: int) -> str:
    """Render default view header with progress bar"""
    progress_bar = render_progress_bar(daily_progress)
    return f"{progress_bar}\n\nTehtävälista\n\nKlikkaa tehtävää merkataksesi sen suoritetuksi.\nKlikkaa tehtyä tehtävää palauttaaksesi sen listalle."


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
    project_steps_remaining = 0
    for step in active_steps:
        total_steps = step.get('total_steps', 0)
        order_index = step.get('order_index', 0)
        # Remaining = total - completed (order_index is 1-based, so completed = order_index - 1)
        # But we count active + pending, so: total - (order_index - 1) = total - order_index + 1
        # Actually, if order_index=2 and total=5, we have: completed=1, active=1, pending=3
        # So remaining = total - (order_index - 1) = 5 - 1 = 4 (active + pending)
        remaining = total_steps - (order_index - 1)
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
    Build home view keyboard with new order:
    1) Completed tasks (newest first): 3 items
    2) Project steps: active step per project
    3) Active tasks: priority order (!!!!, !!!, !!, !, n)
    4) Bottom row: [+][stats][settings][refresh]
    
    Args:
        completed_tasks: List of completed task dicts (with 'id', 'text')
        active_tasks: List of Task objects (already sorted by priority)
        active_steps: List of active project step dicts
    
    Returns:
        InlineKeyboardMarkup
    """
    kb = InlineKeyboardBuilder()
    
    # 1) Completed tasks (newest first): reverse order so newest is first
    for comp_task in reversed(completed_tasks[:3]):
        task_text = _label(comp_task.get('text', ''), 47)
        kb.row(
            InlineKeyboardButton(
                text=f"✓ {task_text}",
                callback_data=f"completed:restore:{comp_task.get('id')}",
            )
        )
    
    # 2) Project steps: active step per project
    # Format: "Projekti 1 · step 1" or similar
    for step in active_steps:
        project_title = step.get('project_title', 'Projekti')
        step_text = step.get('text', '')
        order_index = step.get('order_index', 0)
        step_id = step.get('id', 0)
        
        # Format: "Projekti 1 · step 1" (shortened)
        display_text = f"{project_title} · {step_text}"
        display_text = _label(display_text, 48)
        
        kb.row(
            InlineKeyboardButton(
                text=display_text,
                callback_data=f"ps:{step_id}",
            )
        )
    
    # 3) Active tasks: priority order (already sorted by priority in repo.list_tasks)
    # Render with priority indicators
    for task in active_tasks:
        rendered_title = render_title_with_priority(task.text, task.priority)
        task_text = _label(rendered_title, 48)
        kb.row(
            InlineKeyboardButton(
                text=task_text,
                callback_data=f"t:{task.id}",
            )
        )
    
    # 4) Bottom row: [+][stats][settings][refresh]
    kb.row(
        InlineKeyboardButton(text="+", callback_data="view:add"),
        InlineKeyboardButton(text="stats", callback_data="view:stats"),
        InlineKeyboardButton(text="settings", callback_data="view:settings"),
        InlineKeyboardButton(text="refresh", callback_data="view:refresh"),
        width=4,
    )
    
    return kb.as_markup()


def render_settings_header() -> str:
    return "Asetukset\n\nnollaa - Poistaa kaikki tehtävät ja tilastot"


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


def render_add_type_header() -> str:
    return "Lisää tehtävä\n\nValitse tehtävätyyppi:\n• deadline - määräaikainen tehtävä\n• scheduled - ajastettu tehtävä\n• regular - tavallinen tehtävä"


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
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin tehtäviin", callback_data="view:home"))
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
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin tehtäviin", callback_data="view:home"))
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
    
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin", callback_data="view:home"))
    return kb.as_markup()


def render_suggestions_header(count: int) -> str:
    """Render suggestions view header"""
    return f"💡 Ehdotukset\n\n{count} ehdotusta backlogista.\n\nValitse 'Lisää tehtävälistaan' lisätäksesi tehtävän takaisin listalle."


def project_detail_kb() -> InlineKeyboardMarkup:
    """Project detail view keyboard with back button"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Takaisin listaan", callback_data="view:home"))
    return kb.as_markup()


def render_project_detail(project: dict, steps: list[dict]) -> str:
    """
    Render project detail view with all steps and their statuses.
    
    Args:
        project: Dict with keys: id, title, status, current_step_order, created_at, updated_at
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
