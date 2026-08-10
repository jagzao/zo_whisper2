from transcript_pipeline.language import LanguageDetector


def test_prefix_es_takes_priority():
    detector = LanguageDetector()
    assert detector.detect("es_meeting.mp4") == "es"


def test_prefix_en_takes_priority():
    detector = LanguageDetector()
    assert detector.detect("en_interview.mp3") == "en"


def test_no_prefix_no_folder_returns_none():
    detector = LanguageDetector()
    assert detector.detect("recording.mp3") is None


def test_lang_txt_in_folder(tmp_path):
    (tmp_path / "lang.txt").write_text("en", encoding="utf-8")
    detector = LanguageDetector()
    assert detector.detect("recording.mp3", tmp_path) == "en"


def test_lang_txt_invalid_value_falls_back_to_none(tmp_path):
    (tmp_path / "lang.txt").write_text("fr", encoding="utf-8")
    detector = LanguageDetector()
    assert detector.detect("recording.mp3", tmp_path) is None


def test_lang_txt_cached_per_folder(tmp_path):
    lang_file = tmp_path / "lang.txt"
    lang_file.write_text("es", encoding="utf-8")
    detector = LanguageDetector()
    assert detector.detect("a.mp3", tmp_path) == "es"

    lang_file.write_text("en", encoding="utf-8")  # cambia en disco...
    assert detector.detect("b.mp3", tmp_path) == "es"  # ...pero ya está en cache
