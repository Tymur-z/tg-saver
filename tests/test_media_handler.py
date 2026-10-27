from unittest.mock import MagicMock
from aiogram.types import Message, PhotoSize, Video, Voice
from forwarder.media_handler import MediaHandler


def test_media_handler_type_detection():
    msg_text = MagicMock(spec=Message)
    msg_text.text = "Hello"
    msg_text.photo = None
    msg_text.video = None
    msg_text.video_note = None
    msg_text.voice = None
    msg_text.audio = None
    msg_text.document = None
    msg_text.sticker = None
    msg_text.animation = None
    msg_text.poll = None
    msg_text.location = None
    msg_text.contact = None
    assert MediaHandler.detect_type(msg_text) == "text"

    msg_photo = MagicMock(spec=Message)
    msg_photo.text = None
    msg_photo.photo = [MagicMock(spec=PhotoSize)]
    msg_photo.video = None
    msg_photo.video_note = None
    msg_photo.voice = None
    msg_photo.audio = None
    msg_photo.document = None
    msg_photo.sticker = None
    msg_photo.animation = None
    msg_photo.poll = None
    msg_photo.location = None
    msg_photo.contact = None
    assert MediaHandler.detect_type(msg_photo) == "photo"

    msg_voice = MagicMock(spec=Message)
    msg_voice.text = None
    msg_voice.photo = None
    msg_voice.video = None
    msg_voice.video_note = None
    msg_voice.voice = MagicMock(spec=Voice)
    msg_voice.audio = None
    msg_voice.document = None
    msg_voice.sticker = None
    msg_voice.animation = None
    msg_voice.poll = None
    msg_voice.location = None
    msg_voice.contact = None
    assert MediaHandler.detect_type(msg_voice) == "voice"


def test_clean_and_format_text():
    text = "Скидки тут https://example.com/promo ищи по тегу #sale у @manager!"

    cleaned = MediaHandler.clean_and_format_text(
        text=text,
        clean_links=True,
        clean_tags=True,
        clean_mentions=True,
        append_source_link=True,
        source_title="Крипто Новости",
    )

    assert "https://" not in cleaned
    assert "#sale" not in cleaned
    assert "@manager" not in cleaned
    assert "Источник: Крипто Новости" in cleaned
    assert "Скидки тут" in cleaned
