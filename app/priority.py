"""
Priority parser for task titles.

Derives priority from trailing exclamation marks in task titles.
Each trailing '!' increases priority by +1, clamped to MAX_PRIORITY.
"""

MAX_PRIORITY = 5


def parse_priority(text: str) -> tuple[str, int]:
    """
    Parse priority from trailing exclamation marks in task title.
    
    Args:
        text: Raw task title text (may contain trailing '!' characters)
    
    Returns:
        Tuple of (clean_title, priority) where:
        - clean_title: Title with trailing '!' characters removed
        - priority: Integer from 0 to MAX_PRIORITY (inclusive)
    
    Examples:
        >>> parse_priority("Do something!")
        ('Do something', 1)
        >>> parse_priority("Urgent!!!")
        ('Urgent', 3)
        >>> parse_priority("Task!!!!!!")
        ('Task', 5)  # Clamped to MAX_PRIORITY
        >>> parse_priority("Normal task")
        ('Normal task', 0)
        >>> parse_priority("Task with! middle!")
        ('Task with! middle', 1)  # Trailing ! counts
        >>> parse_priority("Task !")
        ('Task', 1)  # Space before ! still counts
    """
    # Strip leading/trailing whitespace for safe handling
    text = text.strip()
    
    if not text:
        return ("", 0)
    
    # Count trailing exclamation marks only (contiguous sequence at the end)
    # Remove trailing whitespace first to find where the title actually ends
    text_no_trailing_ws = text.rstrip()
    
    # Count contiguous '!' characters at the very end
    trailing_bangs = 0
    for char in reversed(text_no_trailing_ws):
        if char == '!':
            trailing_bangs += 1
        else:
            # Stop at first non-'!' character
            break
    
    # Clamp priority to MAX_PRIORITY
    priority = min(trailing_bangs, MAX_PRIORITY)
    
    # Remove trailing '!' characters to get clean title
    clean_title = text_no_trailing_ws[:-trailing_bangs] if trailing_bangs > 0 else text_no_trailing_ws
    # Strip any remaining trailing whitespace
    clean_title = clean_title.rstrip()
    
    return (clean_title, priority)


def render_title_with_priority(clean_title: str, priority: int) -> str:
    """
    Render task title with priority indicated by trailing exclamation marks.
    
    Args:
        clean_title: Clean task title (without trailing '!')
        priority: Priority level (0 to MAX_PRIORITY)
    
    Returns:
        Title with appropriate number of trailing '!' characters
    
    Examples:
        >>> render_title_with_priority("Do something", 2)
        'Do something!!'
        >>> render_title_with_priority("Task", 0)
        'Task'
        >>> render_title_with_priority("Urgent", 5)
        'Urgent!!!!!'
    """
    if priority <= 0:
        return clean_title
    
    # Clamp priority to valid range
    priority = max(0, min(priority, MAX_PRIORITY))
    
    return clean_title + ('!' * priority)
