import pytest

from Backend.fastapi.routes import stream_routes as sr


@pytest.fixture
def bots(monkeypatch):
    def setup(loads, mbps, failures=None):
        monkeypatch.setattr(sr, "multi_clients", {i: object() for i in loads})
        monkeypatch.setattr(sr, "work_loads", dict(loads))
        monkeypatch.setattr(sr, "client_avg_mbps", dict(mbps))
        monkeypatch.setattr(sr, "client_failures", dict(failures or {}))
        monkeypatch.setattr(sr, "client_dc_map", {})
    return setup


def test_fastest_of_the_least_busy_bots_is_picked(bots):
    bots({0: 0, 1: 0, 2: 0}, {0: 5.0, 1: 20.0, 2: 10.0})
    assert {sr.select_best_client(0) for _ in range(5)} == {1}


def test_a_busy_fast_bot_does_not_beat_an_idle_one(bots):
    bots({0: 0, 1: 2}, {0: 5.0, 1: 50.0})
    assert sr.select_best_client(0) == 0


def test_unmeasured_bots_still_take_turns_so_they_get_measured(bots):
    bots({0: 0, 1: 0, 2: 0}, {0: 30.0, 1: 0.0, 2: 0.0})
    assert len({sr.select_best_client(0) for _ in range(6)}) > 1
