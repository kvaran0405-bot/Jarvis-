"""Voice typing: what gets typed vs. treated as a command."""
from jarvis import dictate


def test_clean_and_commands():
    assert dictate.clean("  hello   world ") == "hello world"
    assert dictate.clean("Thank you.") == "" and dictate.clean("you") == ""     # Whisper hearing silence
    assert dictate.split_command("Jarvis, open Spotify") == "open Spotify"
    assert dictate.split_command("hey jarvis what's next") == "what's next"
    assert dictate.split_command("Dear Mr Tan, thank you for the booking") is None
    assert dictate.split_command("I told Jarvis about it") is None


def test_typing_is_windows_only():
    assert dictate.type_text("hi") is False   # on Linux / in tests nothing is typed
    assert dictate.enabled()
