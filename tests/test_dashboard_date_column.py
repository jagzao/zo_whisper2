from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "transcript_pipeline"
    / "dashboard"
    / "templates"
    / "dashboard.html"
).read_text(encoding="utf-8")


def _header_label(markup: str) -> str:
    without_icon = re.sub(r'<span class="sort-icon">.*?</span>', "", markup)
    return re.sub(r"<[^>]+>", "", without_icon).strip()


def test_date_header_is_sortable_and_immediately_before_actions():
    headers = re.findall(r"<th\b([^>]*)>(.*?)</th>", TEMPLATE)
    table_headers = [(_header_label(label), attrs) for attrs, label in headers]
    labels = [label for label, _ in table_headers]
    assert labels[:9] == [
        "Name", "Type", "Folder", "Project", "Language", "Status", "Transcription", "Date", "Actions"
    ]
    date_attrs = table_headers[7][1]
    assert 'data-sort="date"' in date_attrs
    assert "sortFiles('date')" in date_attrs


def test_date_sort_uses_raw_timestamp_and_existing_sort_modes_remain():
    date_branch = re.search(r"else if \(col === 'date'\) \{(.*?)\n                \}", TEMPLATE, re.S)
    assert date_branch
    assert "a.date_epoch" in date_branch.group(1)
    assert "b.date_epoch" in date_branch.group(1)
    assert "Date.parse(a.date) || 0" in date_branch.group(1)
    assert "Date.parse(b.date) || 0" in date_branch.group(1)
    assert "dir === 'asc' ? -1 : 1" in TEMPLATE
    assert "dir === 'asc' ? 1 : -1" in TEMPLATE
    assert "if (col === 'name')" in TEMPLATE
    assert "else if (col === 'status')" in TEMPLATE
    assert "else if (col === 'size')" in TEMPLATE


def test_date_format_is_localized_and_invalid_values_use_dash():
    helper = re.search(r"function formatMediaDate\(value\) \{(.*?)\n        \}", TEMPLATE, re.S)
    assert helper
    assert "!value" in helper.group(1)
    assert "Date.parse(value)" in helper.group(1)
    assert "return '-'" in helper.group(1)
    assert "toLocaleString('es-MX'" in helper.group(1)
    assert "hour12: false" in helper.group(1)


def test_rendered_row_contains_date_cell_and_status_stays_sixth():
    row = re.search(r"return `<tr>(.*?)</tr>`;", TEMPLATE, re.S)
    assert row
    markup = row.group(1)
    cells = re.findall(r"<td(?:\s|>)", markup)
    assert len(cells) == 9
    assert "${formatMediaDate(f.date)}" in markup
    headers = re.findall(r"<th\b[^>]*>(.*?)</th>", TEMPLATE)
    labels = [_header_label(label) for label in headers]
    assert labels[5] == "Status"
