import types

import pytest

from Backend.helper.metadata.common import TMDB_THRESHOLD, score_candidate
from Backend.helper.metadata.parse import parse_media_name
from Backend.helper.pyro import clean_filename


def test_a_year_mismatch_cannot_beat_a_clearly_better_title():
    # "Avengers: Endgame Encore" is a 2026 re-release of the 2019 film. The old year penalty (-0.5 for 7 years)
    # let the unreleased "Avengers: Secret Wars" (2027, shares only the word "Avengers") win.
    endgame = score_candidate("Avengers Endgame Encore", 2026, "Avengers: Endgame", 2019)
    secret_wars = score_candidate("Avengers Endgame Encore", 2026, "Avengers: Secret Wars", 2027)
    assert endgame > secret_wars


def test_exact_title_is_kept_even_when_the_year_differs():
    assert score_candidate("Avengers Endgame Encore", 2026, "Avengers: Endgame Encore", 2019) >= 0.9


def test_same_title_still_prefers_the_matching_year():
    assert score_candidate("Dune", 2021, "Dune", 2021) > score_candidate("Dune", 2021, "Dune", 1984)
    assert score_candidate("Halloween", 2018, "Halloween", 2018) > score_candidate("Halloween", 2018, "Halloween", 1978)


def test_sharing_only_a_franchise_word_is_not_a_match():
    assert score_candidate("Avengers Endgame Encore", None, "Avengers: Secret Wars", 2027) < TMDB_THRESHOLD


@pytest.mark.parametrize("query,result", [
    ("Spider Man No Way Home", "Spider-Man: No Way Home"),
    ("Pirates Caribbean Curse Black Pearl", "Pirates of the Caribbean: The Curse of the Black Pearl"),
    ("Dune Part Two", "Dune: Part Two"),
])
def test_real_titles_still_match(query, result):
    assert score_candidate(query, None, result, 2020) >= 0.6


async def test_pick_best_chooses_endgame_over_secret_wars(monkeypatch):
    from Backend.helper.metadata.providers import tmdb

    async def no_alts(*_a, **_k):
        return []
    monkeypatch.setattr(tmdb, "_tmdb_alternative_titles", no_alts)

    def movie(id_, title, year):
        return types.SimpleNamespace(id=id_, title=title, original_title=title,
                                     release_date=types.SimpleNamespace(year=year))
    results = [movie(1, "Avengers: Secret Wars", 2027), movie(2, "Avengers: Endgame", 2019), movie(3, "Avengers: Doomsday", 2026)]
    best = await tmdb.pick_best(results, "Avengers Endgame Encore", 2026, "movie")
    assert best.id == 2


@pytest.mark.parametrize("name", [
    "Movie Title (2019) Hindi DD5.1 @Channel 1080p",
    "Movie Title (2019) Hindi @Channel1080p",
    "Movie Title (2019) [@Channel] 1080p Hindi",
    "@Channel Movie Title (2019) Hindi 1080p",
    "Movie.Title.2019.@Channel.1080p.mkv",
])
def test_resolution_after_a_channel_tag_is_not_glued_to_the_word_before(name):
    assert parse_media_name(clean_filename(name))["quality"] == "1080p"


@pytest.mark.parametrize("query", ["Gruham", "The House Next Door", "Aval"])
async def test_translated_titles_match_the_same_film(monkeypatch, query):
    # TMDB has one entry for the bilingual film: English title "Aval", Telugu title "Gruham",
    # Hindi title "The House Next Door" (translations, not alternative titles).
    from Backend.helper.metadata.providers import tmdb

    t = lambda title: types.SimpleNamespace(data=types.SimpleNamespace(title=title, name=None))

    class Target:
        def __init__(self, id_):
            self.id_ = id_

        async def alternative_titles(self):
            return types.SimpleNamespace(titles=[], results=[])

        async def translations(self):
            names = ["Aval", "Gruham", "The House Next Door", None] if self.id_ == 470880 else ["Someone Else"]
            return types.SimpleNamespace(translations=[t(n) for n in names])

    monkeypatch.setattr(tmdb, "get_tmdb_client", lambda: types.SimpleNamespace(movie=Target, tv=Target))
    tmdb.ALT_TITLES_CACHE.clear()

    def movie(id_, title, year):
        return types.SimpleNamespace(id=id_, title=title, original_title=title, release_date=types.SimpleNamespace(year=year))
    best = await tmdb.pick_best([movie(470880, "Aval", 2017), movie(1, "Someone Else", 2017)], query, 2017, "movie")
    assert best is not None and best.id == 470880
