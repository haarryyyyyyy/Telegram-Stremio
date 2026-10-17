import pytest
from app.indexer.parser import parse_release, ParsedMedia


def test_strip_channel_prefix_and_parse_series():
    filename = "@TG_Movies4u_Game_of_Thrones_2011_REPACK_S01E10_2160p_4K_UHD_SDR.mkv"
    parsed = parse_release(filename)

    assert isinstance(parsed, ParsedMedia)
    assert parsed.title == "Game of Thrones"
    assert parsed.year == 2011
    assert parsed.media_type == "series"
    assert parsed.season == 1
    assert parsed.episode == 10
    assert parsed.quality == "4K"


def test_parse_absolute_episode_anime():
    filename = "[SubsPlease] One Piece - 1080 (1080p) [F2A13840].mkv"
    parsed = parse_release(filename)

    assert parsed.title == "One Piece"
    assert parsed.episode == 1080
    assert parsed.media_type == "anime"
    assert parsed.quality == "1080p"


def test_parse_multipart_movie():
    filename = "Viduthalai.Part.1.2023.1080p.WEB-DL.DDP5.1.Atmos.mkv"
    parsed = parse_release(filename)

    assert parsed.title == "Viduthalai Part 1"
    assert parsed.year == 2023
    assert parsed.media_type == "movie"
    assert parsed.season is None
    assert parsed.episode is None
    assert parsed.is_multipart_movie is True
    assert parsed.quality == "1080p"


def test_parse_caption_fallback_for_obfuscated_filename():
    filename = "1234567.mp4"
    caption = "Sakhi (2000) Telugu WEB-DL 1080p DDP 5.1 x264"
    parsed = parse_release(filename, caption=caption)

    assert parsed.title == "Sakhi"
    assert parsed.year == 2000
    assert parsed.media_type == "movie"
    assert parsed.quality == "1080p"
