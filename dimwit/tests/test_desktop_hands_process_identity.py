from dimwit import desktop_hands


def test_same_title_wrong_process_is_rejected(monkeypatch):
    monkeypatch.setattr(desktop_hands, "_window_pid", lambda hwnd: 4242)

    ok, pid = desktop_hands._window_belongs_to_process(
        100, "UnrealEditor", process_name_getter=lambda value: "chrome.exe"
    )

    assert ok is False
    assert pid == 4242


def test_expected_process_identity_is_preserved(monkeypatch):
    monkeypatch.setattr(desktop_hands, "_window_pid", lambda hwnd: 31337)

    ok, pid = desktop_hands._window_belongs_to_process(
        100, "UnrealEditor", process_name_getter=lambda value: "UnrealEditor.exe"
    )

    assert ok is True
    assert pid == 31337
