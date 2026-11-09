path = r"c:\Users\sla_5\Programing\Projects\Tg Saver\bot\handlers\forward.py"

with open(path, "r", encoding="utf-8") as f:
    text = f.read()

start_marker = "def is_transcription_request(text: str, is_reply_to_media: bool = False) -> bool:"
end_marker = "def is_summary_request(text: str) -> bool:"

start_idx = text.find(start_marker)
end_idx = text.find(end_marker)

assert start_idx != -1, "start_marker not found"
assert end_idx != -1, "end_marker not found"

new_fn = '''def is_transcription_request(text: str, is_reply_to_media: bool = False) -> bool:
    """Returns True if user asks to transcribe or what was said in audio/video note, without conversational chat."""
    if not text:
        return False
    t = text.strip().lower()

    # If user asks about chat status / summary / news, NEVER trigger transcription
    if re.search(r"\\b(?:по\\s+чат\\w*|в\\s+чат\\w*|чат\\w*|сводк\\w*|итог\\w*|новост\\w*|нового)\\b", t, re.IGNORECASE):
        if not re.search(r"\\b(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|видеосообщ\\w*)\\b", t, re.IGNORECASE):
            return False

    # Strip bot mentions and name calls
    t = re.sub(r"@[a-zA-Z0-9_]+", "", t).strip()
    t = re.sub(r"^(?:ричард|richard|ричи|рикардо)[,\\s:!-]+", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"(?:^|[\\s,])(?:ричард|richard|ричи|рикардо)(?:[\\s,!?]|$)", " ", t, flags=re.IGNORECASE).strip()

    # Strip polite wrappers and action prefixes
    t = re.sub(
        r"\\b(?:пожалуйста|плиз|пж|сделай|можешь|подскажи|расскажи|покажи|покажь|рокажи|послушай|глянь|посмотри|дай|чётко|четко|хорош|please|pls|can\\s+you|could\\s+you)\\b",
        " ",
        t,
        flags=re.IGNORECASE,
    ).strip()

    clean = re.sub(r"[?!.,;:]+", " ", t).strip()
    clean = " ".join(clean.split())

    # Pure conversational opinions should not trigger direct transcription
    opinion_pattern = re.compile(
        r"\\b(?:что\\s+думаешь|как\\s+тебе|согласен|тво[её]\\s+мнение|мнение|оцени|прокомментируй|what\\s+do\\s+you\\s+think|your\\s+opinion)\\b",
        re.IGNORECASE,
    )
    if opinion_pattern.search(clean):
        return False

    has_media_word = bool(re.search(r"\\b(?:круж\\w*|голосов\\w*|гс|войс\\w*|аудио|видео\\w*|запис\\w*)\\b", clean, re.IGNORECASE))
    has_stt_verb = bool(re.search(r"\\b(?:расшифр\\w*|транскрип\\w*|переведи\\s+в\\s+текст|в\\s+текст|transcribe|transcript)\\b", clean, re.IGNORECASE))

    if is_reply_to_media:
        if has_stt_verb or clean in ("текст", "что там", "что тут", "что он сказал", "что она сказала", "что они сказали"):
            return True
        if re.search(r"\\b(?:что|о\\s*ч[её]м|про\\s+что|сказан\\w*|сказал\\w*|говорит\\w*)\\b", clean, re.IGNORECASE):
            return True

    if has_media_word and (
        has_stt_verb or
        re.search(r"\\b(?:что|о\\s*ч[её]м|про\\s+что|переведи|текст|сказан\\w*|сказал\\w*|говорит\\w*|происходит)\\b", clean, re.IGNORECASE)
    ):
        return True

    if clean in TRANSCRIPTION_KEYWORDS or has_stt_verb:
        return True

    return False

'''

updated = text[:start_idx] + new_fn + text[end_idx:]
with open(path, "w", encoding="utf-8") as f:
    f.write(updated)
print("Updated forward.py successfully via slice replacement")
