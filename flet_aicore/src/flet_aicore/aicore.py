"""
AiCore — Flet Service control wrapping ML Kit GenAI Prompt API
(on-device Gemini Nano via AICore). Android/Pixel only.

Python side just round-trips method calls to the Dart FletService
counterpart (see src/flutter/flet_aicore) which drives
com.google.mlkit:genai-prompt on the platform side.
"""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import flet as ft


class AiCoreStatus(Enum):
    UNAVAILABLE = "unavailable"    # not a supported device, or config not fetched yet
    DOWNLOADABLE = "downloadable"  # supported, model not on-device yet
    DOWNLOADING = "downloading"
    AVAILABLE = "available"        # ready to call generate()


class AiCoreUnavailableError(RuntimeError):
    """Raised when generate() is called but Gemini Nano isn't AVAILABLE."""


@ft.control("aicore")
@dataclass(kw_only=True)
class AiCore(ft.Service):
    """
    On-device GenAI via ML Kit's Prompt API (Gemini Nano / AICore).
    Add one instance to `page.services` (or `page.overlay`) before use.
    No-op / raises AiCoreUnavailableError on non-Pixel or unsupported devices.
    """

    async def check_status(self) -> AiCoreStatus:
        result = await self._invoke_method("check_status")
        return AiCoreStatus(result)

    async def download(self, on_progress=None) -> None:
        """
        Triggers the Gemini Nano feature download if status is DOWNLOADABLE.
        `on_progress(bytes_downloaded: int)` is called for each progress tick
        if provided. Raises RuntimeError if the download fails.

        The model is ~1.5-2GB, so this can take minutes. The "download"
        invoke_method call itself only kicks the download off on the native
        side and returns immediately (Flet's invoke_method dispatch has its
        own short internal timeout — it is not meant for calls that block for
        minutes). Actual completion is reported back via the
        download_progress / download_complete / download_failed events,
        which this method awaits on an asyncio.Event.
        """
        done = asyncio.Event()
        failure = {}

        def _progress(e):
            if on_progress is not None:
                on_progress(e.data.get("bytes", 0))

        def _complete(e):
            done.set()

        def _failed(e):
            failure["message"] = e.data.get("message") or "Download failed"
            done.set()

        # Local Python attribute assignment only — the Dart side triggers
        # these events unconditionally (it doesn't check whether Python
        # registered a handler first), so no `self.update()` round-trip is
        # needed here. Calling update() on a bare Service mid-flight was the
        # actual cause of the "Timeout waiting for invoke method listener"
        # failure introduced by the previous fix.
        self.on_download_progress = _progress
        self.on_download_complete = _complete
        self.on_download_failed = _failed

        await self._invoke_method("download")  # acks once the download has *started*
        await done.wait()
        if "message" in failure:
            raise RuntimeError(failure["message"])

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.3,
        top_k: int = 16,
        max_output_tokens: int = 1024,
    ) -> str:
        """
        Runs one non-streaming generateContent() call against Gemini Nano.
        Raises AiCoreUnavailableError if the model isn't AVAILABLE, or
        RuntimeError for any other AICore-side failure.
        """
        try:
            result = await self._invoke_method(
                "generate",
                arguments={
                    "prompt": prompt,
                    "temperature": temperature,
                    "top_k": top_k,
                    "max_output_tokens": max_output_tokens,
                },
                timeout=60,
            )
        except RuntimeError as ex:
            if "UNAVAILABLE" in str(ex) or "not available" in str(ex).lower():
                raise AiCoreUnavailableError(str(ex)) from ex
            raise
        return result["text"]

    # wired up internally by download() — not meant to be set directly
    on_download_progress: Optional[ft.EventHandler] = field(default=None, repr=False)
    on_download_complete: Optional[ft.EventHandler] = field(default=None, repr=False)
    on_download_failed: Optional[ft.EventHandler] = field(default=None, repr=False)
