from __future__ import annotations

import logging
from typing import Any

import boto3
import httpx
from botocore.config import Config

from app.agent.llm import REPLY_SCHEMA, LLMDecider
from app.agent.loop import Decider, RuleDecider
from app.config import Settings

log = logging.getLogger("metermind.llm")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(
        self, api_key: str, model: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._url = GEMINI_URL.format(model=model)
        self._client = httpx.Client(headers={"x-goog-api-key": api_key}, transport=transport)

    def complete(self, system: str, user: str, timeout: float) -> str:
        response = self._client.post(
            self._url,
            timeout=timeout,
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 200,
                    "responseMimeType": "application/json",
                    "responseSchema": REPLY_SCHEMA,
                },
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data["candidates"][0]["content"]["parts"][0]["text"])


class BedrockProvider:
    name = "bedrock"

    def __init__(self, settings: Settings) -> None:
        self._model = settings.bedrock_model_id
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(
                connect_timeout=2,
                read_timeout=settings.llm_timeout_seconds,
                retries={"max_attempts": 0},
            ),
        )

    def complete(self, system: str, user: str, timeout: float) -> str:
        response = self._client.converse(
            modelId=self._model,
            system=[{"text": system + "\nReply with a single JSON object and nothing else."}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 200, "temperature": 0},
        )
        return str(response["output"]["message"]["content"][0]["text"])


def build_decider(settings: Settings) -> Decider:
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            log.warning("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty; using rules only")
            return RuleDecider()
        provider: GeminiProvider | BedrockProvider = GeminiProvider(
            settings.gemini_api_key.get_secret_value(), settings.gemini_model
        )
    elif settings.llm_provider == "bedrock":
        provider = BedrockProvider(settings)
    else:
        return RuleDecider()
    return LLMDecider(provider, settings.llm_timeout_seconds)
