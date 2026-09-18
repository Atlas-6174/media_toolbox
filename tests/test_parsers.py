import re
import pytest
from src.tools.ffmpeg import tiempo_a_segundos

def test_tiempo_a_segundos():
    assert tiempo_a_segundos("00:00:10.00") == 10.0
    assert tiempo_a_segundos("00:01:05.50") == 65.5
    assert tiempo_a_segundos("01:00:00.00") == 3600.0
    assert tiempo_a_segundos("invalid") == 0.0

def test_ffmpeg_duration_regex():
    line = "  Duration: 00:02:15.34, start: 0.000000, bitrate: 1245 kb/s"
    regex = re.compile(r"Duration:\s+(\d{2}:\d{2}:\d{2}\.\d+)")
    match = regex.search(line)
    assert match is not None
    assert match.group(1) == "00:02:15.34"

def test_ffmpeg_time_regex():
    line = "out_time=00:01:20.50"
    regex = re.compile(r"out_time=(\d{2}:\d{2}:\d{2}\.\d+)")
    match = regex.search(line)
    assert match is not None
    assert match.group(1) == "00:01:20.50"

def test_ytdlp_regex():
    line = "[download]  65.4% of   20.50MiB at    2.34MiB/s ETA 00:03"
    regex = re.compile(r"\[download\]\s+([\d\.]+)%")
    match = regex.search(line)
    assert match is not None
    assert float(match.group(1)) == 65.4

def test_calibre_regex():
    line = "34% Converting input to HTML..."
    regex = re.compile(r"(\d{1,3})%\s*(.*)")
    match = regex.search(line)
    assert match is not None
    assert int(match.group(1)) == 34
    assert match.group(2) == "Converting input to HTML..."
