from datetime import datetime, timezone

from app.worker.guard import State, pilot_until


def test_open_launch_access_still_requires_an_expiry_and_is_not_paid(monkeypatch):
    monkeypatch.delenv('PILOT_WORKSPACE_IDS', raising=False)
    monkeypatch.setenv('PILOT_ACCESS_UNTIL', '2026-10-21T00:00:00+00:00')
    monkeypatch.delenv('PILOT_OPEN_ACCESS', raising=False)
    assert pilot_until(123) is None
    monkeypatch.setenv('PILOT_OPEN_ACCESS', '1')
    until = pilot_until(123)
    assert until == datetime(2026, 10, 21, tzinfo=timezone.utc)
    state = State('active', None, None, None, None, None,
                  datetime(2026, 10, 20, tzinfo=timezone.utc), until)
    assert state.has_analysis_access and not state.paid
    assert not State('active', None, None, None, None, None, until, until).has_analysis_access
    for invalid in ('', 'bad', '2026-10-21'):
        monkeypatch.setenv('PILOT_ACCESS_UNTIL', invalid)
        assert pilot_until(123) is None
