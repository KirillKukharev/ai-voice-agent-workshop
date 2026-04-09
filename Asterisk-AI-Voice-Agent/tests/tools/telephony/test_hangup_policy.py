from src.tools.telephony.hangup_policy import (
    assistant_short_terminal_farewell,
    resolve_hangup_policy,
    text_contains_marker,
    text_contains_end_call_intent,
    text_is_short_polite_closing,
)


def test_default_end_call_markers_include_natural_closing_phrases():
    policy = resolve_hangup_policy({})
    markers = (policy.get("markers") or {}).get("end_call", [])

    assert "thank you" in markers
    assert "thanks" in markers
    assert "have a good day" in markers


def test_end_call_detection_matches_polite_goodbye_phrase():
    policy = resolve_hangup_policy({})
    markers = (policy.get("markers") or {}).get("end_call", [])

    assert text_contains_marker("Okay. Thank you. Have a good day.", markers)


def test_end_call_detection_does_not_trigger_on_unrelated_text():
    policy = resolve_hangup_policy({})
    markers = (policy.get("markers") or {}).get("end_call", [])

    assert not text_contains_marker("Can you explain setup pricing again?", markers)


def test_end_call_detection_handles_common_stt_misrecognitions():
    policy = resolve_hangup_policy({})
    markers = (policy.get("markers") or {}).get("end_call", [])

    assert text_contains_end_call_intent("Okay, hand up the call.", markers)
    assert text_contains_end_call_intent("Please and the call now.", markers)


def test_short_polite_closing_detection_accepts_terminal_thanks():
    assert text_is_short_polite_closing("Okay, thank you")
    assert text_is_short_polite_closing("thanks goodbye")


def test_short_polite_closing_detection_rejects_long_mid_call_phrases():
    assert not text_is_short_polite_closing("Thanks, can you also explain pricing and setup again")


def test_assistant_short_terminal_farewell_accepts_russian_goodbye():
    assert assistant_short_terminal_farewell("До свидания!")
    assert assistant_short_terminal_farewell("до свидания")


def test_assistant_short_terminal_farewell_rejects_mid_booking_phrase():
    # "до встречи" alone must not trigger assistant-only hangup
    assert not assistant_short_terminal_farewell("До встречи на тест-драйве завтра в десять")


def test_assistant_short_terminal_farewell_rejects_long_closing_paragraph():
    text = "Спасибо за звонок. Мы ждем вас. " * 5
    assert not assistant_short_terminal_farewell(text)
