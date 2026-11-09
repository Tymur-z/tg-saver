from __future__ import annotations

import base64
import io
import logging
from typing import Dict, List, Optional
from PIL import Image, ImageOps
from aiogram import Bot
from aiogram.types import PhotoSize
from moderation.llm_client import LLMClient

logger = logging.getLogger(__name__)


class VisionService:
    """Сервис для оптимизации, кэширования и подготовки изображений для мультимодальных LLM."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        enabled: bool = True,
        max_dimension: int = 1024,
        detail: str = "auto",
        jpeg_quality: int = 85,
    ) -> None:
        self.llm_client = llm_client
        self.enabled = enabled
        self.max_dimension = max_dimension
        self.detail = detail
        self.jpeg_quality = jpeg_quality
        self._cache: Dict[str, str] = {}  # file_unique_id -> base64 jpeg
        self._cache_order: List[str] = []
        self._max_cache_entries = 100

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if not self.llm_client or not self.llm_client.api_key:
            return False
        return True

    def get_cached_image(self, cache_key: str) -> Optional[str]:
        return self._cache.get(cache_key)

    def set_cached_image(self, cache_key: str, base64_data: str) -> None:
        if cache_key in self._cache:
            return
        if len(self._cache_order) >= self._max_cache_entries:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)
        self._cache[cache_key] = base64_data
        self._cache_order.append(cache_key)

    def optimize_image_bytes(
        self,
        image_bytes: bytes,
        max_dimension: Optional[int] = None,
        quality: Optional[int] = None,
    ) -> Optional[str]:
        """Загружает байты изображения, корректирует EXIF-ориентацию,

        пропорционально масштабирует и конвертирует в компактный JPEG base64.
        """
        if not image_bytes:
            return None

        max_dim = max_dimension or self.max_dimension
        q = quality or self.jpeg_quality

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                # Коррекция ориентации кадра по EXIF (актуально для фото со смартфонов)
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

                # Приведение к RGB (поддержка RGBA, палитры P и CMYK)
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Пропорциональное уменьшение до экономичного разрешения
                w, h = img.size
                if max_dim > 0 and (w > max_dim or h > max_dim):
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                out_buf = io.BytesIO()
                img.save(out_buf, format="JPEG", quality=q, optimize=True)
                encoded = base64.b64encode(out_buf.getvalue()).decode("utf-8")
                return encoded
        except Exception as e:
            logger.warning("Error optimizing image bytes for vision: %s", e)
            return None

    async def download_and_process_photo(
        self,
        bot: Bot,
        photo_sizes: Optional[List[PhotoSize]] = None,
        file_id: Optional[str] = None,
        file_unique_id: Optional[str] = None,
        max_dimension: Optional[int] = None,
    ) -> Optional[str]:
        """Скачивает подходящий размер фото из Telegram (по списку PhotoSize или прямому file_id),

        оптимизирует и кэширует base64.
        """
        if not photo_sizes and not file_id:
            return None

        target_max = max_dimension or self.max_dimension
        target_file_id = file_id
        cache_key = file_unique_id or file_id

        if photo_sizes:
            # Выбираем оптимальный размер фото:
            best_size = photo_sizes[-1]
            for ps in photo_sizes:
                if ps.width and ps.height and max(ps.width, ps.height) >= target_max:
                    best_size = ps
                    break
            target_file_id = best_size.file_id
            cache_key = getattr(best_size, "file_unique_id", None) or best_size.file_id

        if not target_file_id:
            return None

        cached = self.get_cached_image(cache_key)
        if cached:
            return cached

        try:
            tg_file = await bot.get_file(target_file_id)
            if not tg_file.file_path:
                return None

            buf = io.BytesIO()
            await bot.download_file(tg_file.file_path, destination=buf)
            raw_bytes = buf.getvalue()
            if not raw_bytes:
                return None

            b64 = self.optimize_image_bytes(raw_bytes, max_dimension=target_max)
            if b64:
                self.set_cached_image(cache_key, b64)
            return b64
        except Exception as e:
            logger.warning("Failed to download or process Telegram photo %s: %s", target_file_id, e)
            return None
