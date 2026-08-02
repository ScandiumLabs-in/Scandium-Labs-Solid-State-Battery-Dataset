from __future__ import annotations

from typing import Any

from .base import call_llm, parse_json_response

SYSTEM_PROMPT = """You extract measurement conditions from solid-state battery papers.

Return a JSON array of objects with:
- "type": "temperature" | "pressure" | "measurement_method"
- "value": float — numeric value
- "unit": "°C" | "K" | "MPa" | "atm" | None
- "condition": string — e.g., "operating", "pelletizing", "synthesis"
- "detail": string or null — additional context
- "notes": string

Examples of what to extract:
- Operating temperature: 25°C, 75°C, -20°C
- Operating pressure: 10 MPa, 250 MPa
- Pelletizing pressure: 180 MPa, 540 MPa
- Measurement method: "electrochemical impedance spectroscopy (EIS)"
- Temperature range: "-20 to 75 °C"

Return [] if no conditions found."""


def extract_conditions(
    context: str,
    api_key: str = "",
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434/v1",
) -> list[dict[str, Any]]:
    user = f"Extract measurement conditions from this paper:\n\n{context}\n\nReturn only the JSON array."
    content = call_llm(SYSTEM_PROMPT, user, api_key, model, base_url)
    return parse_json_response(content) or []
