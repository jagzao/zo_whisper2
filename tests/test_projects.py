from pathlib import Path

from transcript_pipeline.projects import load_projects, match_project, validate_project

PROJECTS = [
    {
        "name": "Northwind",
        "match": {"folder_contains": ["py_northwind"], "prefix": ["northwind_"]},
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
    audio = Path("audio/northwind_20260101_standup.mp3")
    project = match_project(audio, PROJECTS)
    assert project is not None
    assert project["name"] == "Northwind"


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


def test_validate_project_accepts_minimal_valid_entry():
    assert validate_project({"name": "X"}) == []


def test_validate_project_accepts_full_example():
    project = {
        "name": "Northwind",
        "match": {"prefix": ["northwind_"], "folder_contains": ["py_northwind"]},
        "handler": "client_meeting",
        "language": "en",
        "output_path": "C:/Dev/ClientProjects/Northwind",
        "data_classification": "confidential",
        "custom_fillers": ["like", "right"],
        "corrections": {"Samm": "Sam"},
    }
    assert validate_project(project) == []


def test_validate_project_rejects_missing_name():
    errors = validate_project({"match": {}})
    assert any("name" in e for e in errors)


def test_validate_project_rejects_non_dict():
    assert validate_project("not a project") != []
    assert validate_project(None) != []


def test_validate_project_rejects_unknown_handler():
    errors = validate_project({"name": "X", "handler": "arbitrary_code_exec"})
    assert any("handler" in e for e in errors)


def test_validate_project_rejects_bad_match_shape():
    errors = validate_project({"name": "X", "match": {"prefix": "not_a_list"}})
    assert any("match.prefix" in e for e in errors)


def test_validate_project_rejects_invalid_data_classification():
    errors = validate_project({"name": "X", "data_classification": "top-secret"})
    assert any("data_classification" in e for e in errors)


def test_validate_project_rejects_bad_corrections_shape():
    errors = validate_project({"name": "X", "corrections": {"a": 123}})
    assert any("corrections" in e for e in errors)


def test_load_projects_skips_invalid_entries(tmp_path):
    config = tmp_path / "projects.json"
    config.write_text(
        '{"projects": [{"name": "Good"}, {"handler": "no_name"}, {"name": "Bad", "handler": "evil"}]}',
        encoding="utf-8",
    )
    projects = load_projects(config)
    assert [p["name"] for p in projects] == ["Good"]
