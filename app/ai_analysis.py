# -*- coding: utf-8 -*-
"""
AI analysis for task statistics using OpenAI Responses API.
API key from OPENAI_API_KEY; do not log user data or the key.
"""
from __future__ import annotations

import json
import os
from typing import Any

# Default model and strict output limit
AI_ANALYSIS_MODEL = "gpt-4o-mini"
AI_ANALYSIS_MAX_OUTPUT_TOKENS = 400
FALLBACK_MESSAGE = (
    "AI-analyysi ei juuri nyt saatavilla. Yritä myöhemmin uudelleen."
)

# --- Prompt constants (FI) ---

DEVELOPER_PROMPT_FI = (
    "Toimit Dotolistin analytiikka-assistenttina. Tavoite: rajattu mutta kattava analyysi tehtävätilastoista.\n"
    "Käytä VAIN annettua dataa, älä arvaa.\n"
    "Kieli: suomi. Ei emojeita. Ei pitkäveteisiä selityksiä.\n"
    "Pituus: max 1200 merkkiä.\n"
    "Muoto EXACT:\n"
    "Yhteenveto: 1–2 lausetta.\n"
    "Havainnot:\n"
    "- ...\n"
    "- ...\n"
    "Suositukset:\n"
    "- ...\n"
    "- ...\n"
    "Riskit tai puutteet:\n"
    "- ... (jos dataa puuttuu, muuten jätä pois)\n\n"
    "Jos dataa on liian vähän, sano se Yhteenveto-kohdassa ja anna 1 lyhyt suositus datan keruuseen."
)

USER_PROMPT_TEMPLATE_FI = (
    "Analysoi seuraavat tilastot ajalta {period_label}. Data (JSON) on rajattu — älä arvaa puuttuvia kenttiä.\n"
    "Data:\n"
    '"""\n'
    "{stats_json}\n"
    '"""'
)


def build_ai_messages(stats_payload: dict[str, Any], period_label: str) -> tuple[str, str]:
    """
    Build developer (system) and user prompts for the Responses API.

    Args:
        stats_payload: Dict with keys e.g. completed, deleted, active, days
        period_label: Human-readable period, e.g. "1 päivä", "1 viikko"

    Returns:
        (instructions, user_message) for responses.create(instructions=..., input=...)
    """
    stats_json = json.dumps(stats_payload, ensure_ascii=False)
    user_message = USER_PROMPT_TEMPLATE_FI.format(
        period_label=period_label,
        stats_json=stats_json,
    )
    return DEVELOPER_PROMPT_FI, user_message


def run_ai_analysis(stats_payload: dict[str, Any], period_label: str) -> str:
    """
    Call OpenAI Responses API and return the analysis text.
    On any error or missing API key, returns a safe fallback message.
    Does not log API key or user data.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        return FALLBACK_MESSAGE

    try:
        from openai import OpenAI
    except ImportError:
        return FALLBACK_MESSAGE

    instructions, user_message = build_ai_messages(stats_payload, period_label)
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.create(
            model=AI_ANALYSIS_MODEL,
            instructions=instructions,
            input=user_message,
            max_output_tokens=AI_ANALYSIS_MAX_OUTPUT_TOKENS,
            temperature=0.5,
        )
    except Exception:
        return FALLBACK_MESSAGE

    if not response or getattr(response, "output", None) is None:
        return FALLBACK_MESSAGE

    # Prefer SDK convenience property; else walk output for output_text
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    for item in getattr(response, "output", []) or []:
        if getattr(item, "content", None):
            for block in item.content:
                if getattr(block, "type", None) == "output_text":
                    t = getattr(block, "text", None)
                    if isinstance(t, str) and t.strip():
                        return t.strip()

    return FALLBACK_MESSAGE
