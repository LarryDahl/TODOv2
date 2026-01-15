from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.ui.telegram.keyboards.common import main_menu_kb


async def go_to_main_menu(
    message: Message,
    state: FSMContext | None = None,
    text: str = "OK."
) -> None:
    """
    Clears FSM state (if provided) and returns user to the main menu.
    Safe to call from anywhere.
    """
    if state is not None:
        await state.clear()

    await message.answer(
        text,
        reply_markup=main_menu_kb()
    )
