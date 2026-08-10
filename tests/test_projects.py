from pathlib import Path

from transcript_pipeline.projects import load_projects, match_project

PROJECTS = [
    {
        "name": "Valeris",
        "match": {"folder_contains": ["py_valeris"], "prefix": ["valeris_"]},
    },
    {
        "name": "Zo Interviews",
        "match": {
            "folder_contains": ["py_zo", "zo_Entrevista"],
            "prefix": ["zo_"],
            "filename_contains": ["interview", "entrevista"],
        },
    },
    {
        "name": "Tutorials",
        "match": {"filename_contains": ["tutorial"]},
    },
]


def test_match_by_prefix():
    audio = Path("audio/valeris_20260101_standup.mp3")
    project = match_project(audio, PROJECTS)
    assert project is not None
    assert project["name"] == "Valeris"


def test_match_by_folder_contains():
    audio = Path("Videos/py_zo/some_recording.mp4")
    project = match_project(audio, PROJECTS)
    assert project["name"] == "Zo Interviews"


def test_match_by_filename_contains():
    audio = Path("audio/mi_tutorial_python.mp4")
    project = match_project(audio, PROJECTS)
    assert project["name"] == "Tutorials"


def test_no_match_returns_none():
    audio = Path("audio/random_file.mp3")
    assert match_project(audio, PROJECTS) is None


def test_first_matching_rule_wins():
    # "zo_" prefix matches "Zo Interviews" before folder/keyword rules of others are checked
    audio = Path("audio/zo_random.mp3")
    project = match_project(audio, PROJECTS)
    assert project["name"] == "Zo Interviews"


def test_load_projects_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "projects.json"
    assert load_projects(missing) == []


def test_load_projects_reads_json(tmp_path):
    config = tmp_path / "projects.json"
    config.write_text('{"projects": [{"name": "X", "match": {}}]}', encoding="utf-8")
    projects = load_projects(config)
    assert projects == [{"name": "X", "match": {}}]
