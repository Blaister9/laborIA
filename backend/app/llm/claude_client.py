"""
claude_client.py — Wrapper asíncrono del SDK de Anthropic.

Expone:
  - create(): llamada no-streaming (para el loop de tool use)
  - stream(): context manager de streaming (para la respuesta final)
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from anthropic.types import Message


class ClaudeClient:
    """Cliente asíncrono para la API de Anthropic."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY no está configurada. "
                "Agrégala al archivo .env en la raíz del proyecto."
            )
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def create(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> Message:
        """
        Llamada no-streaming. Retorna el mensaje completo.
        Se usa durante el loop de tool use para obtener la respuesta
        antes de ejecutar las herramientas.
        """
        kwargs: dict = dict(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools

        return await self._client.messages.create(**kwargs)

    def stream(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ):
        """
        Context manager de streaming. Uso:

            async with client.stream(system=..., messages=...) as stream:
                async for text in stream.text_stream:
                    yield text
        """
        kwargs: dict = dict(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools

        return self._client.messages.stream(**kwargs)
