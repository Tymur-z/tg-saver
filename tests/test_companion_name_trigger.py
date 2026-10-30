# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from moderation.companion import ChatCompanion

def make_msg(text, chat_type="group"):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.caption = None
    msg.chat = MagicMock(spec=Chat, type=chat_type, id=-100123)
    msg.from_user = MagicMock(spec=User, id=111, first_name="Alex", username="alex")
    msg.reply_to_message = None
    msg.entities = None
    return msg

def test_companion_triggers_by_name():
    companion = ChatCompanion()
    
    # "Ричард"
    msg1 = make_msg("Ричард, как дела?")
    trig1, prompt1 = companion.is_triggered(msg1, bot_username="RichardHelperBot", bot_id=777)
    assert trig1 is True
    assert "как дела?" in prompt1
    
    # "Richard"
    msg2 = make_msg("Richard what is the weather today?")
    trig2, prompt2 = companion.is_triggered(msg2, bot_username="RichardHelperBot", bot_id=777)
    assert trig2 is True
    assert "weather" in prompt2

    # In middle: "привет, Ричард, подскажи"
    msg3 = make_msg("привет, Ричард, подскажи тему")
    trig3, prompt3 = companion.is_triggered(msg3, bot_username="RichardHelperBot", bot_id=777)
    assert trig3 is True
    assert "подскажи тему" in prompt3

    # Negative: not addressed
    msg4 = make_msg("обычное сообщение в чате без упоминания")
    trig4, prompt4 = companion.is_triggered(msg4, bot_username="RichardHelperBot", bot_id=777)
    assert trig4 is False
    assert prompt4 == ""