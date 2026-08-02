from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx


def call_llm(
    system_prompt: str,
    user_prompt: str,
    api_key: str = "",
    model: str = "llama3.2:3b",
    base_url: str = "http://localhost:11434/v1",
    temperature: float = 0.0,
    timeout: int = 600,
    max_retries: int = 3,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error = ""
    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                json={"model": model, "messages": messages, "temperature": temperature},
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            return content
        except httpx.ReadTimeout:
            last_error = f"timeout after {timeout}s (attempt {attempt + 1}/{max_retries})"
            print(f"  [llm] ReadTimeout: {last_error} — retrying..." if attempt < max_retries - 1 else f"  [llm] {last_error}")
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code} (attempt {attempt + 1}/{max_retries})"
            print(f"  [llm] {last_error}")
            if e.response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                raise
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                print(f"  [llm] Error: {e} — retrying...")
                time.sleep(5)
            else:
                raise

    raise httpx.ReadTimeout(last_error)


def parse_json_response(content: str) -> Any:
    if not content.strip():
        return []
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                return []
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                return []
        return []
