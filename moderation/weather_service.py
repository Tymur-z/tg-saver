"""Модуль получения реальной погоды для городов участников (UK: Alton, Havant, Hindhead)."""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional, Tuple
import aiohttp

logger = logging.getLogger(__name__)

CITIES: Dict[str, Dict[str, object]] = {
    "alton": {
        "name_ru": "Олтоне (Alton)",
        "lat": 51.15,
        "lon": -0.98,
    },
    "havant": {
        "name_ru": "Хаванте (Havant)",
        "lat": 50.85,
        "lon": -0.98,
    },
    "hindhead": {
        "name_ru": "Хайндхеде (Hindhead)",
        "lat": 51.11,
        "lon": -0.73,
    },
}

USER_DEFAULT_CITIES: Dict[int, str] = {
    5956803305: "alton",     # MixaRed (Миша Красный)
    5985808271: "alton",     # Forsazh (Миша Форсаж)
    1696889505: "havant",    # Sol (Соль)
    5848551858: "hindhead",  # Abyss (Миша 3-й)
}

WMO_WEATHER_CODES: Dict[int, str] = {
    0: "ясно",
    1: "в основном ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "туман с изморозью",
    51: "легкая морось",
    53: "моросящий дождь",
    55: "сильная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный ливень",
    71: "небольшой снег",
    73: "снегопад",
    75: "сильный снегопад",
    80: "кратковременные дожди",
    81: "ливневый дождь",
    82: "шквальный ливень",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}

WEATHER_KEYWORD_PATTERN = re.compile(
    r"\b(?:погод[аеуыо]|градус[а-я]*|на\s+улице|дожд[ьяеи]|снег[а-я]*|температур[а-я]*|weather|темп|холодно|жарко|тепло|ветрен[а-я]*|лив[ен]\w*|пасмурн\w*|солн[це]\w*|шторм\w*)\b",
    re.IGNORECASE,
)

# In-memory cache: city_key -> (timestamp, data_dict)
_WEATHER_CACHE: Dict[str, Tuple[float, dict]] = {}
CACHE_TTL = 600  # 10 minutes


def is_weather_query(text: str) -> bool:
    """Проверяет, спрашивает ли пользователь о погоде или температуре."""
    if not text:
        return False
    return bool(WEATHER_KEYWORD_PATTERN.search(text))


def resolve_target_city(text: str, user_id: Optional[int] = None) -> Tuple[str, str, float, float]:
    """
    Определяет город по тексту запроса или по ID участника.
    Возвращает (city_key, name_ru, lat, lon).
    """
    lower = text.lower() if text else ""
    if re.search(r"\b(?:хавант\w*|havant)\b", lower):
        city_key = "havant"
    elif re.search(r"\b(?:хайндхед\w*|хаендхед\w*|hindhead)\b", lower):
        city_key = "hindhead"
    elif re.search(r"\b(?:олтон\w*|alton)\b", lower):
        city_key = "alton"
    elif user_id and user_id in USER_DEFAULT_CITIES:
        city_key = USER_DEFAULT_CITIES[user_id]
    else:
        # Default to Alton (where MixaRed & Forsazh live)
        city_key = "alton"

    info = CITIES[city_key]
    return city_key, str(info["name_ru"]), float(info["lat"]), float(info["lon"])


async def fetch_current_weather(lat: float, lon: float, city_key: str) -> Optional[dict]:
    """Запрашивает актуальную погоду из бесплатного Open-Meteo API с кэшированием."""
    now = time.time()
    if city_key in _WEATHER_CACHE:
        ts, cached = _WEATHER_CACHE[city_key]
        if now - ts < CACHE_TTL:
            return cached

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cw = data.get("current_weather", {})
                    if cw:
                        _WEATHER_CACHE[city_key] = (now, cw)
                        return cw
    except Exception as e:
        logger.debug("Failed to fetch weather from Open-Meteo for %s: %s", city_key, e)

    return None


async def get_weather_summary(prompt: str, user_id: Optional[int] = None) -> Optional[str]:
    """
    Если сообщение содержит вопрос о погоде, возвращает контекстную сводку
    с реальной температурой и условиями в UK (Alton/Havant/Hindhead).
    """
    if not is_weather_query(prompt):
        return None

    city_key, city_name_ru, lat, lon = resolve_target_city(prompt, user_id=user_id)
    cw = await fetch_current_weather(lat, lon, city_key)

    if cw:
        temp = cw.get("temperature", "?")
        wcode = cw.get("weathercode", 0)
        wind = cw.get("windspeed", 0)
        condition = WMO_WEATHER_CODES.get(wcode, "облачно")
        return (
            f"[РЕАЛЬНАЯ ПОГОДА ПРЯМО СЕЙЧАС В {city_name_ru.upper()} (Великобритания): "
            f"{temp}°C, {condition}, ветер {wind} км/ч. "
            f"Опирайся строго на эти реальные факты! Ответь в живом пацанском стиле, "
            f"КАТЕГОРИЧЕСКИ БЕЗ пошлых и порнографических метафор!]"
        )

    return (
        f"[ЛОКАЦИЯ: Собеседник спрашивает про погоду в {city_name_ru} (Великобритания / Англия). "
        f"Опирайся на типичный климат Англии (дожди, сырость, прохлада), "
        f"КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать пошлые или бредовые фразы вроде 'порнографического шторма'!]"
    )
