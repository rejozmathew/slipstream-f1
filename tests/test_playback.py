from slipstream.events import NormalizedEvent
from slipstream.playback import ReplayController


def sample_events() -> list[NormalizedEvent]:
    return [
        NormalizedEvent(
            "session", "2025-01-01T00:00:00Z", "test", {"status": "STARTED"}
        ),
        NormalizedEvent("driver", "2025-01-01T00:00:00Z", "test", {"number": "4"}),
        NormalizedEvent(
            "timing", "2025-01-01T00:00:02Z", "test", {"number": "4", "lap": 1}
        ),
        NormalizedEvent(
            "timing", "2025-01-01T00:00:04Z", "test", {"number": "4", "lap": 2}
        ),
    ]


def test_seek_rebuilds_inclusive_state() -> None:
    controller = ReplayController(sample_events())

    state = controller.seek("2025-01-01T00:00:02Z")

    assert controller.cursor == 3
    assert state.drivers["4"].lap == 1


def test_play_honors_speed_and_can_pause_then_resume() -> None:
    sleeps: list[float] = []
    controller = ReplayController(sample_events(), sleep=sleeps.append)
    seen_laps: list[int | None] = []

    def pause_after_lap_one(state: object) -> None:
        lap = state.drivers.get("4").lap if "4" in state.drivers else None  # type: ignore[attr-defined]
        seen_laps.append(lap)
        if lap == 1:
            controller.pause()

    controller.play(speed=2.0, on_state=pause_after_lap_one)

    assert controller.finished is False
    assert sleeps == [1.0]
    controller.play(speed=2.0)
    assert controller.finished is True
    assert controller.state.drivers["4"].lap == 2
    assert sleeps == [1.0, 1.0]


def test_cursor_seek_reconstructs_exact_event_count() -> None:
    controller = ReplayController(sample_events())

    state = controller.seek_cursor(3)

    assert controller.cursor == 3
    assert state.drivers["4"].lap == 1
    controller.seek_cursor(0)
    assert controller.state.drivers == {}


def test_delay_seeks_relative_to_newest_event() -> None:
    controller = ReplayController(sample_events())

    state = controller.seek_delay(2)

    assert controller.cursor == 3
    assert state.drivers["4"].lap == 1


def test_relative_seek_and_batched_clock_advance_use_session_time() -> None:
    controller = ReplayController(sample_events())
    controller.seek(controller.events[0].occurred_at)

    controller.seek_relative(2)
    assert controller.state.drivers["4"].lap == 1

    controller.advance(2)
    assert controller.state.drivers["4"].lap == 2
    assert controller.finished is True
