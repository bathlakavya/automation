"""Local LLM access through the configured Ollama model."""
import json
import logging
import os
import re
import time
from pathlib import Path

import requests

log = logging.getLogger("copilot")
ROOT = Path(__file__).resolve().parent.parent


def load_prompt(name):
    return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if not m:
            raise
        return json.loads(m.group(1))


def hermes(system, user, json_mode=False, retries=3):
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
    payload = {
        "model": os.getenv("HERMES_MODEL", "hermes3:8b"),
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    if json_mode:
        payload["format"] = "json"
    last = None
    for i in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=300)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("Hermes attempt %d failed: %s", i + 1, e)
            time.sleep(2 ** i)
    raise RuntimeError(f"Hermes unavailable: {last}")


def execute(user, json_mode=False):
    """Run requests only through the configured Ollama model."""
    return hermes(load_prompt("hermes_system"), user, json_mode=json_mode)


def audit(draft, raw, kind):
    """Ask the configured Ollama model to check its draft against source data."""
    user = f"KIND: {kind}\n\nRAW DATA:\n{raw}\n\nDRAFT:\n{draft}"
    return hermes(load_prompt("audit"), user)
