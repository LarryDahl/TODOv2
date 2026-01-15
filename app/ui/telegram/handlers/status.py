from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.domain.oppari.service import OppariService

router = Router()

STATUS_CB = "nav:status"  # pidä sama kuin napin callback_data


async def render_status_text(opp_service: OppariService) -> str:
    enabled = await opp_service.list_enabled_agents()  # tai whatever teillä on
    running = await opp_service.is_running()           # tai repo/state
    lines = ["Status", "Enabled agents:"]
    if enabled:
        for a in enabled:
            lines.append(f"- {a.agent_id} ({a.category})")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Oppari running." if running else "Oppari not running.")
    return "\n".join(lines)


@router.message(Command("status"))
async def status_cmd(message: Message, opp_service: OppariService):
    text = await render_status_text(opp_service)
    await message.answer(text)


@router.callback_query(lambda c: (c.data or "") == STATUS_CB)
async def status_cb(cb: CallbackQuery, opp_service: OppariService):
    await cb.answer()
    text = await render_status_text(opp_service)
    # joko uusi viesti tai muokkaa vanhaa – tässä uusi on ok:
    await cb.message.answer(text)
