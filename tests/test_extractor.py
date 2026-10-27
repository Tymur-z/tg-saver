from datetime import datetime
from analytics.extractor import FeatureExtractor


def test_extractor_punctuation_and_emojis():
    text = "Привет всем! Как дела? Всё отлично))) 🚀🔥"
    now = datetime(2026, 10, 27, 14, 30)

    feat = FeatureExtractor.extract(text, now)

    assert feat.char_count == len(text)
    assert feat.word_count >= 6
    assert feat.exclamation_count == 1
    assert feat.question_count == 1
    assert feat.bracket_smiles_count >= 1
    assert feat.emoji_count == 2
    assert "🚀" in feat.emojis
    assert "🔥" in feat.emojis
    assert feat.informal_greetings_count == 1
    assert feat.created_hour == 14


def test_extractor_formality_and_slang():
    text = "Здравствуйте, спасибо за информацию, спс и плз проверьте это!"
    now = datetime(2026, 10, 27, 9, 15)

    feat = FeatureExtractor.extract(text, now)

    assert feat.formal_greetings_count == 1
    assert feat.polite_markers_count >= 1
    assert feat.slang_markers_count >= 2
    assert feat.has_trailing_dot is False


def test_extractor_no_trailing_dot():
    text1 = "Короткое сообщение без точки"
    text2 = "Нормативное предложение с точкой."

    feat1 = FeatureExtractor.extract(text1, datetime.now())
    feat2 = FeatureExtractor.extract(text2, datetime.now())

    assert feat1.has_trailing_dot is False
    assert feat2.has_trailing_dot is True
