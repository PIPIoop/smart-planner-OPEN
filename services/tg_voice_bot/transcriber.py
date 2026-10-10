from __future__ import annotations

import asyncio
from pathlib import Path

from typing import Any


class TranscriptionError(RuntimeError):
    """Ошибка распознавания аудио."""


class VoiceTranscriber:
    """
    Адаптер над faster-whisper.

    Telegram-бот не должен знать детали Whisper:
    модель, beam search, VAD и формат сегментов.
    Он вызывает только метод transcribe().
    """

    def __init__(
        self,
        *,
        model_name: str,
        language: str | None,
        device: str,
        compute_type: str,
    ) -> None:
        self._language = language

        # Тяжёлая зависимость импортируется только при реальном запуске
        # распознавания, а не при импорте модуля/тестах Telegram-логики.
        from faster_whisper import WhisperModel

        self._model: Any = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

        # Не запускаем несколько тяжёлых распознаваний одновременно.
        # Для локальной разработки и одного пользователя этого достаточно.
        self._transcription_lock = asyncio.Lock()

    async def transcribe(self, audio_path: Path) -> str:
        """
        Асинхронная оболочка над синхронным распознаванием Whisper.

        Распознавание нагружает CPU/GPU. Если запустить его прямо
        внутри async handler, цикл событий Telegram-бота заблокируется.
        Поэтому вычисление переносится в отдельный поток.
        """

        if not audio_path.exists():
            raise TranscriptionError(
                f"Аудиофайл не найден: {audio_path}"
            )

        async with self._transcription_lock:
            try:
                return await asyncio.to_thread(
                    self._transcribe_sync,
                    audio_path,
                )
            except Exception as error:
                raise TranscriptionError(
                    "Не удалось распознать голосовое сообщение."
                ) from error

    def _transcribe_sync(self, audio_path: Path) -> str:
        segments, info = self._model.transcribe(
            str(audio_path),
            language=self._language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True,
        )

        # segments является генератором. Реальное распознавание
        # выполняется во время обхода генератора.
        text_parts = [
            segment.text.strip()
            for segment in segments
            if segment.text.strip()
        ]

        text = " ".join(text_parts).strip()

        if not text:
            detected_language = getattr(
                info,
                "language",
                "unknown",
            )

            raise TranscriptionError(
                "Модель не обнаружила речь. "
                f"Определённый язык: {detected_language}."
            )

        return text