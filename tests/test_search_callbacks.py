from types import SimpleNamespace

from plugins.search import _build_kb, _parse_callback_data


def make_file(name):
    return SimpleNamespace(file_name=name)


def test_parse_callback_data_supports_search_actions():
    payload = _parse_callback_data("page|100|200|2")
    assert payload == {"action": "page", "chat_id": 100, "msg_id": 200, "value": "2"}


def test_build_kb_keeps_filters_and_pagination_state():
    state = {
        "all_files": [make_file(f"Movie {i} 1080p English S01E01") for i in range(25)],
        "lang": "English",
        "qual": "1080p",
        "season": "S01",
        "ep": "E01",
        "page": 1,
    }

    kb = _build_kb(state, 99, 100)
    buttons = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "page|100|99|0" in buttons
    assert "page|100|99|2" in buttons
    assert "pginfo|100|99" in buttons
