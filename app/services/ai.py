"""Replaceable AI layer. Implement AIProvider to add a new vendor; nothing else changes."""
import base64
import json
import logging
import re
from abc import ABC, abstractmethod

import httpx

from app.config import get_settings

log = logging.getLogger("ai")


class AIError(Exception):
    pass


class AIProvider(ABC):
    @abstractmethod
    async def chat(self, system: str, user: str, max_tokens: int = 600) -> str: ...

    @abstractmethod
    async def vision(self, system: str, user: str, image: bytes, mime: str = "image/jpeg") -> str: ...


class OpenAICompatible(AIProvider):
    def __init__(self, key, base_url, model, vision_model):
        self.key, self.base, self.model, self.vmodel = key, base_url.rstrip("/"), model, vision_model or model

    async def _post(self, payload):
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{self.base}/chat/completions", json=payload,
                             headers={"Authorization": f"Bearer {self.key}"})
        if r.status_code >= 400:
            raise AIError(f"AI API error {r.status_code}")
        return r.json()["choices"][0]["message"]["content"] or ""

    async def chat(self, system, user, max_tokens=600):
        return await self._post({"model": self.model, "max_tokens": max_tokens, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}]})

    async def vision(self, system, user, image, mime="image/jpeg"):
        b64 = base64.b64encode(image).decode()
        return await self._post({"model": self.vmodel, "max_tokens": 600, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": user},
                                         {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]})


class AnthropicProvider(AIProvider):
    def __init__(self, key, model, vision_model):
        self.key, self.model, self.vmodel = key, model, vision_model or model

    async def _post(self, model, system, content, max_tokens):
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.anthropic.com/v1/messages",
                             headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                             json={"model": model, "max_tokens": max_tokens, "system": system,
                                   "messages": [{"role": "user", "content": content}]})
        if r.status_code >= 400:
            raise AIError(f"AI API error {r.status_code}")
        return "".join(b.get("text", "") for b in r.json()["content"])

    async def chat(self, system, user, max_tokens=600):
        return await self._post(self.model, system, user, max_tokens)

    async def vision(self, system, user, image, mime="image/jpeg"):
        content = [{"type": "image", "source": {"type": "base64", "media_type": mime,
                                                "data": base64.b64encode(image).decode()}},
                   {"type": "text", "text": user}]
        return await self._post(self.vmodel, system, content, 600)


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIError("AI did not return JSON")
    return json.loads(m.group(0))


class AIService:
    def __init__(self, overrides: dict | None = None):
        s, o = get_settings(), overrides or {}
        self.enabled = bool(s.ai_api_key)
        provider = o.get("ai_provider") or s.ai_provider
        model = o.get("ai_model") or s.ai_model
        vmodel = o.get("ai_vision_model") or s.ai_vision_model
        base = o.get("ai_base_url") or s.ai_base_url
        self.provider: AIProvider | None = None
        if self.enabled:
            self.provider = (AnthropicProvider(s.ai_api_key, model, vmodel) if provider == "anthropic"
                             else OpenAICompatible(s.ai_api_key, base, model, vmodel))
        self.name = f"{provider}:{model}"

    def _need(self):
        if not self.provider:
            raise AIError("AI not configured")
        return self.provider

    async def analyze_screenshot(self, image: bytes, channel_name: str, mime: str) -> dict:
        system = ("You are a strict fraud-aware reviewer. Return ONLY JSON with keys: "
                  "is_youtube_screenshot(bool), channel_matches(bool), shows_subscribed_state(bool), "
                  "manipulation_suspected(bool), confidence(0-1), reasons(string). "
                  "Be conservative: if unsure, set shows_subscribed_state=false. Never invent details.")
        user = (f"Does this screenshot show the YouTube channel '{channel_name}' with a 'Subscribed' state "
                "(not 'Subscribe')? Check for editing artifacts, mismatched fonts, cropped UI, or a different channel.")
        return _json(await self._need().vision(system, user, image, mime))

    async def expand_query(self, query: str) -> list[str]:
        out = await self._need().chat(
            "Translate the user's search into English and return 1-5 short keywords as a JSON list of strings. "
            "Context: Minecraft clients, patches, texture packs, APKs, FPS boosters. JSON only.", query, 150)
        m = re.search(r"\[.*\]", out, re.S)
        return [str(x) for x in json.loads(m.group(0))][:5] if m else []

    async def describe(self, notes: str) -> str:
        return await self._need().chat(
            "Write a concise, appealing 2-3 sentence file description for a Minecraft download store. "
            "Use only facts in the notes; do not invent features. Plain text.", notes, 250)

    async def suggest_category(self, notes: str, categories: list[str]) -> str:
        return await self._need().chat(
            "Pick the best category for this file from the list. Reply with the category name only.\n"
            "Categories: " + "; ".join(categories), notes, 40)

    async def is_spam(self, text: str) -> bool:
        d = _json(await self._need().chat('Return JSON {"spam": bool}. Spam = ads, scams, link floods.', text, 40))
        return bool(d.get("spam"))

    async def assist(self, question: str, lang: str, catalog: str) -> str:
        return await self._need().chat(
            f"You are the support assistant of RUK MODERS GANG, a Minecraft file store bot. Reply in language code '{lang}', "
            "briefly. Help with finding files, installing packs/APKs, and using the bot. If unsure, say so. "
            f"Available files: {catalog}", question, 400)
