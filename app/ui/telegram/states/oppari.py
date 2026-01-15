from aiogram.fsm.state import StatesGroup, State


class OppariFlow(StatesGroup):
    # start flow
    start_choose_time = State()
    start_enter_time = State()
    start_planned_task = State()

    # end flow
    end_choose_time = State()
    end_enter_time = State()
    end_description = State()
    end_learned = State()
    end_challenges = State()
    end_next_steps = State()
    end_completed_as_planned = State()
    end_not_completed_reason = State()
    end_break_minutes = State()
