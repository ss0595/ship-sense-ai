"""OpenAI-powered explanation layer for ShipSense AI.

The deterministic risk model remains the source of truth for scores and
factors. OpenAI is used only to turn that evidence into a clearer agent-style
explanation and mitigation plan for the dashboard.
"""

from __future__ import annotations

import json
import os
import re
import ssl
from logging import Logger
from urllib.request import Request, urlopen

from backend.config import key_configured


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"


def openai_source_status() -> dict:
    """Return safe OpenAI status without exposing the key."""
    return {
        "configured": key_configured("OPENAI_API_KEY"),
        "provider": "OpenAI Responses API",
        "model": os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL,
    }


def enrich_result_with_openai(result: dict, logger: Logger) -> dict:
    """Use OpenAI to refine explanation/recommendations when a key is present."""
    status = openai_source_status()
    result["ai_agent"] = {**status, "used": False}
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return result

    try:
        ai_output = _call_openai(api_key, status["model"], _agent_context(result))
        if ai_output.get("explanation"):
            result["explanation"] = ai_output["explanation"]
        if ai_output.get("recommendations"):
            result["recommendations"] = ai_output["recommendations"]
        if ai_output.get("judge_summary"):
            result["judge_summary"] = ai_output["judge_summary"]
        result["ai_agent"]["used"] = True
    except Exception as exc:
        logger.warning("OpenAI explanation failed; using deterministic fallback: %s", exc)
        result["ai_agent"]["error"] = "OpenAI fallback used"

    return result


def _agent_context(result: dict) -> dict:
    """Create a compact, non-secret prompt payload for the OpenAI call."""
    return {
        "role": "ShipSense AI multimodal delay-risk agent",
        "instruction": "Use only these facts. Do not invent hubs, APIs, incidents, or data.",
        "shipment": result.get("shipment", {}),
        "score": result.get("score"),
        "level": result.get("level"),
        "probability": result.get("probability"),
        "confidence": result.get("confidence"),
        "validation": result.get("validation", {}),
        "top_factors": [
            {
                "name": factor.get("name"),
                "contribution": factor.get("contribution"),
                "evidence": factor.get("evidence"),
            }
            for factor in result.get("factors", [])[:4]
        ],
        "current_recommendations": result.get("recommendations", [])[:6],
        "alternate_hubs": [item.get("hub") or item.get("port") for item in result.get("alternatives", [])[:3]],
        "data_sources": result.get("data_sources", []),
        "required_json_shape": {
            "explanation": "45-65 words for the dashboard",
            "recommendations": "4-6 action bullets as strings",
            "judge_summary": "one 25-40 word line explaining why OpenAI is used",
        },
    }


def _call_openai(api_key: str, model: str, context: dict) -> dict:
    payload = {
        "model": model,
        "instructions": (
            "You are a professional multimodal logistics risk intelligence agent. "
            "Return valid JSON only. Keep the risk score and evidence consistent "
            "with the provided context. Never expose secrets."
        ),
        "input": json.dumps(context, ensure_ascii=True),
        "max_output_tokens": 550,
    }
    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=12, context=_ssl_context()) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    return _parse_agent_json(_response_text(response_payload))


def _ssl_context() -> ssl.SSLContext:
    """Use certifi certificates on local Python installs when available."""
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _response_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])

    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if "text" in content:
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()


def _parse_agent_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)

    explanation = str(payload.get("explanation", "")).strip()
    judge_summary = str(payload.get("judge_summary", "")).strip()
    recommendations = [
        str(item).strip()
        for item in payload.get("recommendations", [])
        if str(item).strip()
    ][:6]
    return {
        "explanation": explanation,
        "recommendations": recommendations,
        "judge_summary": judge_summary,
    }
