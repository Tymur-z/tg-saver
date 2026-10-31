from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Dict, Optional, Tuple
from aiogram import Bot

logger = logging.getLogger(__name__)


def get_ffmpeg_executable() -> str:
    """Finds available ffmpeg binary on system or falls back to imageio_ffmpeg."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    for common_path in ("/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.exists(common_path):
            return common_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return "ffmpeg"


class NvidiaSTTService:
    """Speech-to-Text service powered by NVIDIA Whisper Large v3 over NVIDIA Riva gRPC."""

    def __init__(
        self,
        api_key: str = "",
        function_id: str = "b702f636-f60c-4a3d-a6f4-f3568c13bd7d",
        uri: str = "grpc.nvcf.nvidia.com:443",
        language_code: str = "ru-RU",
        enabled: bool = True,
    ) -> None:
        self.api_key = api_key.strip()
        self.function_id = function_id.strip()
        self.uri = uri.strip()
        self.language_code = language_code.strip() or "ru-RU"
        self.enabled = enabled
        self._cache: Dict[str, str] = {}  # file_unique_id or hash -> transcribed text
        self._cache_order: list[str] = []
        self._max_cache_entries = 500
        self._asr_service = None
        self._init_client()

    def _init_client(self) -> None:
        if not self.api_key:
            self._asr_service = None
            return
        try:
            import riva.client
            auth = riva.client.Auth(
                uri=self.uri,
                use_ssl=True,
                metadata_args=[
                    ["function-id", self.function_id],
                    ["authorization", f"Bearer {self.api_key}"],
                ],
            )
            self._asr_service = riva.client.ASRService(auth)
            logger.info("NvidiaSTTService initialized successfully with function_id=%s", self.function_id)
        except Exception as e:
            logger.warning("Could not initialize riva.client ASRService: %s", e)
            self._asr_service = None

    def update_config(
        self,
        api_key: Optional[str] = None,
        function_id: Optional[str] = None,
        uri: Optional[str] = None,
        language_code: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        reinit = False
        if api_key is not None and api_key != self.api_key:
            self.api_key = api_key.strip()
            reinit = True
        if function_id is not None and function_id != self.function_id:
            self.function_id = function_id.strip()
            reinit = True
        if uri is not None and uri != self.uri:
            self.uri = uri.strip()
            reinit = True
        if language_code is not None:
            self.language_code = language_code.strip() or "ru-RU"
        if enabled is not None:
            self.enabled = enabled

        if reinit:
            self._init_client()

    def is_available(self) -> bool:
        return bool(self.enabled and self.api_key and self._asr_service is not None)

    def get_cached_transcript(self, cache_key: str) -> Optional[str]:
        return self._cache.get(cache_key)

    def set_cached_transcript(self, cache_key: str, text: str) -> None:
        if not cache_key:
            return
        if cache_key in self._cache:
            self._cache[cache_key] = text
            return
        if len(self._cache_order) >= self._max_cache_entries:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)
        self._cache[cache_key] = text
        self._cache_order.append(cache_key)

    async def convert_to_pcm16_wav(self, input_bytes: bytes, input_suffix: str = ".oga") -> Optional[bytes]:
        """Converts arbitrary audio/video container to 16kHz mono linear PCM WAV using ffmpeg."""
        ffmpeg_bin = get_ffmpeg_executable()
        in_file = None
        out_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix=input_suffix, delete=False) as f_in:
                in_file = f_in.name
                f_in.write(input_bytes)
                f_in.flush()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_out:
                out_file = f_out.name

            # Run ffmpeg conversion
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", in_file,
                "-vn",  # disable video stream if video_note
                "-ac", "1",  # mono
                "-ar", "16000",  # 16kHz
                "-f", "wav",
                out_file,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

            if proc.returncode != 0:
                logger.warning("FFmpeg conversion failed (code %s): %s", proc.returncode, stderr.decode(errors="ignore")[:300])
                return None

            with open(out_file, "rb") as f_res:
                wav_data = f_res.read()
            return wav_data
        except asyncio.TimeoutError:
            logger.error("FFmpeg conversion timed out")
            return None
        except Exception as e:
            logger.exception("Error converting audio to WAV: %s", e)
            return None
        finally:
            if in_file and os.path.exists(in_file):
                try:
                    os.remove(in_file)
                except Exception:
                    pass
            if out_file and os.path.exists(out_file):
                try:
                    os.remove(out_file)
                except Exception:
                    pass

    def _sync_recognize(self, wav_bytes: bytes, language_code: str) -> Optional[str]:
        if not self._asr_service:
            return None
        try:
            import riva.client
            config = riva.client.RecognitionConfig(
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
                sample_rate_hertz=16000,
                language_code=language_code,
                max_alternatives=1,
                enable_automatic_punctuation=True,
            )
            response = self._asr_service.offline_recognize(wav_bytes, config)
            if not response or not response.results:
                return None
            transcripts = []
            for res in response.results:
                if res.alternatives:
                    text = res.alternatives[0].transcript.strip()
                    if text:
                        transcripts.append(text)
            return " ".join(transcripts).strip() if transcripts else None
        except Exception as e:
            logger.warning("NVIDIA Riva offline_recognize error with lang %s: %s", language_code, e)
            # If ru-RU failed, try multi or en-US as fallback
            if language_code not in ("multi", "en-US"):
                try:
                    import riva.client
                    config = riva.client.RecognitionConfig(
                        encoding=riva.client.AudioEncoding.LINEAR_PCM,
                        sample_rate_hertz=16000,
                        language_code="multi",
                        max_alternatives=1,
                        enable_automatic_punctuation=True,
                    )
                    fallback_resp = self._asr_service.offline_recognize(wav_bytes, config)
                    if fallback_resp and fallback_resp.results:
                        transcripts = [r.alternatives[0].transcript.strip() for r in fallback_resp.results if r.alternatives]
                        return " ".join(transcripts).strip() if transcripts else None
                except Exception as fb_err:
                    logger.debug("Fallback to 'multi' also failed: %s", fb_err)
            return None

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        input_suffix: str = ".oga",
        language_code: Optional[str] = None,
        cache_key: Optional[str] = None,
    ) -> Optional[str]:
        """Converts input audio/video note bytes and transcribes via NVIDIA Whisper."""
        if not self.is_available():
            logger.debug("STT Service is not available or disabled")
            return None

        if cache_key:
            cached = self.get_cached_transcript(cache_key)
            if cached:
                return cached

        wav_bytes = await self.convert_to_pcm16_wav(audio_bytes, input_suffix=input_suffix)
        if not wav_bytes or len(wav_bytes) < 44:  # minimum WAV header size
            logger.warning("Converted WAV is empty or invalid")
            return None

        lang = language_code or self.language_code or "ru-RU"
        text = await asyncio.to_thread(self._sync_recognize, wav_bytes, lang)
        if text and cache_key:
            self.set_cached_transcript(cache_key, text)
        return text

    async def transcribe_telegram_file(
        self,
        bot: Bot,
        file_id: str,
        file_unique_id: str,
        suffix: str = ".oga",
        language_code: Optional[str] = None,
    ) -> Optional[str]:
        """Downloads a Telegram file and transcribes it."""
        if not self.is_available():
            return None

        cached = self.get_cached_transcript(file_unique_id)
        if cached:
            return cached

        try:
            tg_file = await bot.get_file(file_id)
            if not tg_file.file_path:
                return None

            import io
            buf = io.BytesIO()
            await bot.download_file(tg_file.file_path, destination=buf)
            audio_bytes = buf.getvalue()
            if not audio_bytes:
                return None

            return await self.transcribe_audio_bytes(
                audio_bytes=audio_bytes,
                input_suffix=suffix,
                language_code=language_code,
                cache_key=file_unique_id,
            )
        except Exception as e:
            logger.exception("Failed to download or transcribe Telegram file %s: %s", file_id, e)
            return None
