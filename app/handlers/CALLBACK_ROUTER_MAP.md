# Callback Router Map

## Standardized Callback Prefixes

### Navigation & Home
- `home:` - Main navigation
  - `home:home` - Return to home view
  - `home:refresh` - Refresh home view (re-render existing message)
  - `home:plus` - Open plus menu (add task/project/edit)
  - `home:edit` - Open edit tasks view

### Add Task/Project Flow
- `add:` - Add task/project actions
  - `add:task_type` - Open task type selection (Regular/Scheduled/Deadline)
  - `add:regular` - Start regular task flow
  - `add:scheduled` - Start scheduled task flow
  - `add:deadline` - Start deadline task flow
  - `add:project` - Start project creation flow
  - `add:type:<type>` - Set task type (legacy)
  - `add:difficulty:<n>` - Set difficulty (legacy)
  - `add:category:<cat>` - Set category (legacy)
  - `add:scheduled:date:<offset>` - Select scheduled date
  - `add:scheduled:time:<time>` - Select scheduled time
  - `add:deadline:date:<offset>` - Select deadline date
  - `add:deadline:time:<time>` - Select deadline time

### Edit Tasks
- `edit:` - Edit task actions
  - `edit:task:<task_id>` - Open task edit menu
  - `edit:del:<task_id>` - Delete task
  - `edit:back` - Back to edit list

### Task Actions
- `task:` - Task-specific actions
  - `task:del:<task_id>` - Delete task (from task detail view)
  - `task:done:<task_id>` - Mark task as done

### Completed Tasks
- `done:` - Completed tasks view
  - `done:page:<offset>` - Pagination for completed tasks
  - `done:restore:<event_id>` - Restore completed task

### Deleted Tasks
- `deleted:` - Deleted tasks view
  - `deleted:page:<offset>` - Pagination for deleted tasks
  - `deleted:restore:<event_id>` - Restore deleted task

### Projects
- `proj:` - Project actions
  - `proj:detail:<project_id>` - Show project detail view
  - `proj:step:done:<step_id>` - Mark project step as done
  - `proj:step:del:<step_id>` - Delete project step
  - `proj:cancel:<project_id>` - Cancel project

### Settings
- `settings:` - Settings actions
  - `settings:timezone` - Open timezone selection
  - `settings:tz:<timezone>` - Set timezone
  - `settings:toggle_show_done` - Toggle show done in home
  - `settings:export_db` - Export database (placeholder)
  - `settings:reset` - Reset all data (from old settings view)

### Stats
- `stats:` - Statistics actions
  - `stats:all_time` - Show all time statistics
  - `stats:ai` - Open AI analysis menu
  - `stats:ai:<period>` - Run AI analysis for period (1, 7, 30, 365, custom)
  - `stats:reset` - Show reset stats confirmation
  - `stats:reset_confirm` - Confirm reset stats
  - `stats:period:<days>` - Legacy period stats (7, 30, 90, 180, 365)

### Suggestions
- `suggestion:` - Suggestion actions
  - `suggestion:accept:<event_id>` - Accept suggestion
  - `suggestion:snooze:<event_id>` - Snooze suggestion
  - `suggestion:ignore:<event_id>` - Ignore suggestion

### Legacy/Deprecated
- `view:` - Legacy view navigation (being phased out, use `home:` instead)
  - `view:home` - Return to home (use `home:home` instead)
  - `view:refresh` - Refresh (use `home:refresh` instead)
  - `view:edit` - Edit view (use `home:edit` instead)
  - `view:done` - Done view
  - `view:deleted` - Deleted view
  - `view:stats` - Stats view
  - `view:settings` - Settings view
  - `view:add` - Add menu (use `home:plus` instead)
  - `view:add_backlog` - Add project (use `add:project` instead)

- `p:` - Legacy project detail (use `proj:detail:` instead)
- `ps:` - Legacy project step (use `proj:step:` instead)
- `completed:` - Legacy completed restore (use `done:restore:` instead)

## Router Registration Order

1. `views.router` - View navigation handlers
2. `tasks.router` - Task action handlers
3. `deadline.router` - Deadline flow handlers
4. `schedule.router` - Schedule flow handlers
5. `add_task.router` - Add task/project handlers
6. `suggestions.router` - Suggestion handlers
7. `text_messages.router` - Catch-all text message handler (MUST be last)

## Navigation Rules

- All "Takaisin" (Back) buttons should use `home:home` to return to home
- No "Takaisin" buttons should return to previous view (always go to home)
- Refresh button uses `home:refresh` to re-render existing message
