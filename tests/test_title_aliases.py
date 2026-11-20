import types

from Backend.helper import title_aliases


class FakeColl:
    def __init__(self):
        self.docs = {}

    async def update_one(self, flt, upd, upsert=False):
        self.docs[flt["_id"]] = {"_id": flt["_id"], **upd["$set"]}

    async def find_one(self, flt):
        return self.docs.get(flt["_id"])


def _use(monkeypatch):
    coll = FakeColl()
    monkeypatch.setattr(title_aliases, "_coll", lambda: coll)
    return coll


async def test_a_fixed_movie_title_maps_to_its_id_next_time(monkeypatch):
    _use(monkeypatch)
    await title_aliases.remember("Gruham", 2017, "movie", imdb_id="tt6889474", tmdb_id=470880)
    assert await title_aliases.lookup("gruham", 2017, "movie") == "tt6889474"
    assert await title_aliases.lookup("Gruham", 1999, "movie") is None        # a different film with the same name


async def test_series_aliases_ignore_the_year_and_fall_back_to_tmdb(monkeypatch):
    _use(monkeypatch)
    await title_aliases.remember("Kaala Paani", None, "tv", imdb_id=None, tmdb_id=225171)
    assert await title_aliases.lookup("Kaala Paani", 2023, "tv") == "225171"
    assert await title_aliases.lookup("Kaala Paani", None, "movie") is None   # never applied across types


async def test_lookup_survives_a_database_error(monkeypatch):
    class Broken:
        async def find_one(self, *_a):
            raise RuntimeError("db down")
    monkeypatch.setattr(title_aliases, "_coll", lambda: Broken())
    assert await title_aliases.lookup("x y", None, "movie") is None


async def test_metadata_uses_a_remembered_id(monkeypatch):
    from Backend.helper.metadata import entry
    seen = {}

    async def lookup(title, year, media_type):
        return "tt6889474" if (title, media_type) == ("Gruham", "movie") else None

    async def resolve_movie(title, enc, year=None, quality=None, default_id=None):
        seen["default_id"] = default_id
        return {"title": "Aval", "media_type": "movie", "quality": quality}

    monkeypatch.setattr(entry.title_aliases, "lookup", lookup)
    monkeypatch.setattr(entry, "resolve_movie", resolve_movie)
    await entry.metadata("Gruham (2017) Telugu 1080p.mkv", 123, 1)
    assert seen["default_id"] == "tt6889474"
