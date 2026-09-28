import json

from app.chat.streaming import sse, text_deltas


def test_sse_frames_one_json_event():
    frame = sse({"type": "text-delta", "id": "t1", "delta": "Umsatz ↑"})
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    assert json.loads(frame.removeprefix("data: ")) == {"type": "text-delta", "id": "t1", "delta": "Umsatz ↑"}


def test_text_deltas_rejoin_to_the_original_text():
    text = "Revenue  grew in 2024. "
    deltas = text_deltas(text)
    assert len(deltas) > 1
    assert "".join(deltas) == text
