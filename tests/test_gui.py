"""Desktop-app tests (offscreen Qt).

These run under ``QT_QPA_PLATFORM=offscreen`` so they work on a headless
runner. They are skipped when PySide6 is not installed, which keeps the lean
CI matrix fast; a dedicated CI job installs PySide6 and runs them.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="optional GUI dependency")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import tools as app_tools  # noqa: E402
from app.main import TOOL_SPECS, Main  # noqa: E402
from app.thumbnails import ThumbnailPane  # noqa: E402
from app.worker import format_result  # noqa: E402
from core import ops  # noqa: E402

TMP = Path(__file__).parent / "tmp" / "gui"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def samples() -> dict:
    TMP.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(4):
        doc.new_page().insert_text(fitz.Point(72, 72), f"gui fixture {i + 1}")
    path = TMP / "gui-fixture.pdf"
    doc.save(str(path))
    doc.close()
    return {"pdf": str(path)}


@pytest.fixture
def window(qt_app, samples: dict):
    win = Main()
    win.files.add_paths([samples["pdf"]])
    win.show()  # isVisible() on child widgets needs a shown top-level window
    QApplication.processEvents()
    yield win
    win.close()
    win.deleteLater()


def test_window_lists_available_tools_and_reports_backends(window):
    from app.tools import unavailable_tools

    assert window.tools.count() == len(TOOL_SPECS)
    assert window.files.count() == 1

    log = window.log.toPlainText()
    assert "nothing is uploaded" in log
    assert "PyMuPDF" in log
    for label in unavailable_tools():
        assert label in window.tool_hint.text() or f"⚠ {label}" in log


def test_each_tool_shows_only_its_own_fields(window):
    for row, spec in enumerate(TOOL_SPECS):
        window.tools.setCurrentRow(row)
        assert set(window.visible_fields()) == set(spec.fields), spec.label


def test_switching_tools_keeps_entered_values(window):
    window.tools.setCurrentRow(next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Watermark"))
    window._fields["text"][0].setText("CONFIDENTIAL")

    window.tools.setCurrentRow(next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Compress"))
    window.tools.setCurrentRow(next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Watermark"))
    assert window._fields["text"][0].text() == "CONFIDENTIAL"


def test_info_tool_hides_the_output_row(window):
    window.tools.setCurrentRow(next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Info"))
    assert not window.output.isVisible()

    window.tools.setCurrentRow(next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Compress"))
    assert window.output.isVisible()


def test_filter_hides_unrelated_tools(window):
    window.filter.setText("form")
    visible = [
        spec.label for row, spec in enumerate(TOOL_SPECS) if not window.tools.item(row).isHidden()
    ]
    assert visible == [s.label for s in TOOL_SPECS if "form" in s.label.lower()]
    window.filter.setText("")
    assert all(not window.tools.item(row).isHidden() for row in range(window.tools.count()))


def test_run_button_executes_a_tool_through_the_worker(window, samples: dict, tmp_path: Path):
    window.tools.setCurrentRow(next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Compress"))
    target = tmp_path / "gui-compressed.pdf"
    window.output.setText(str(target))
    window._run()  # runs on a worker thread
    assert window._worker is not None
    window._worker.wait(20000)
    window._worker.done.emit(window._worker)  # deliver any queued signal
    QApplication.processEvents()

    assert target.exists(), window.log.toPlainText()
    assert "done" in window.log.toPlainText()
    assert window.btn_run.isEnabled()


def test_thumbnail_pane_loads_pages_and_reorders(qt_app, samples: dict, tmp_path: Path):
    pane = ThumbnailPane()
    pane.load(samples["pdf"])
    pane._renderer.wait(20000)
    QApplication.processEvents()

    assert pane.list.count() == 4
    assert pane.order() == [1, 2, 3, 4]

    pane.list.setCurrentRow(0)
    pane.move_selection(1)
    assert pane.order() == [2, 1, 3, 4]

    pane.reverse()
    assert pane.order() == [4, 3, 1, 2]

    pane.reset_order()
    assert pane.order() == [1, 2, 3, 4]

    target = tmp_path / "reordered.pdf"
    saved = pane.save_reordered(str(target))
    assert saved == str(target)
    assert ops.info(str(target))["pages"] == 4

    pane.list.setCurrentRow(0)
    pane.move_selection(2)
    pane.save_reordered(str(tmp_path / "reordered2.pdf"))
    assert ops.info(str(tmp_path / "reordered2.pdf"))["pages"] == 4
    pane.close()


def test_thumbnail_pane_reports_missing_files(qt_app, tmp_path: Path):
    pane = ThumbnailPane()
    messages: list[str] = []
    pane.status.connect(messages.append)
    pane.load(str(tmp_path / "nope.pdf"))
    assert messages and "No such file" in messages[0]
    assert pane.save_reordered(str(tmp_path / "out.pdf")) is None
    pane.close()


def test_reorder_tool_uses_the_thumbnail_order(window, samples: dict, tmp_path: Path):
    pane = window.thumbs
    pane.load(samples["pdf"])
    pane._renderer.wait(20000)
    QApplication.processEvents()
    pane.reverse()  # 4,3,2,1

    window.tools.setCurrentRow(
        next(i for i, s in enumerate(TOOL_SPECS) if s.label == "Reorder pages")
    )
    target = tmp_path / "from-thumbnails.pdf"
    window.output.setText(str(target))
    window._run()
    window._worker.wait(20000)
    QApplication.processEvents()

    assert target.exists(), window.log.toPlainText()
    with fitz.open(str(target)) as doc:
        assert [page.get_text("text").strip() for page in doc] == [
            "gui fixture 4",
            "gui fixture 3",
            "gui fixture 2",
            "gui fixture 1",
        ]


def test_worker_reports_failures_and_results():
    from app.worker import Worker

    results: list = []
    errors: list[str] = []
    worker = Worker(lambda value: {"echo": value}, "hello")
    worker.done.connect(results.append)
    worker.failed.connect(errors.append)
    worker.run()  # same-thread call: signals are delivered immediately
    assert results == [{"echo": "hello"}]
    assert errors == []

    def boom():
        raise ValueError("expected failure")

    failing = Worker(boom)
    failing.failed.connect(errors.append)
    failing.run()
    assert errors and "expected failure" in errors[-1]


def test_format_result_covers_paths_lists_dicts_and_long_text():
    assert format_result("out.pdf") == "out.pdf"
    assert format_result(["a.pdf", "b.pdf"]) == "a.pdf\nb.pdf"
    assert '"pages": 2' in format_result({"pages": 2})

    long_text = "x" * 5000
    rendered = format_result(long_text)
    assert "more characters" in rendered
    assert len(rendered) < len(long_text)


def test_tool_availability_helpers_match_the_missing_set(monkeypatch):
    monkeypatch.setattr(app_tools.ocr, "tesseract_available", lambda *a, **k: True)
    monkeypatch.setattr(app_tools.convert, "libreoffice_available", lambda: True)
    monkeypatch.setattr(app_tools.sign, "signing_available", lambda: True)
    assert app_tools.unavailable_tools() == {}
    for tool in app_tools.TOOLS:
        assert app_tools.requirements_met(tool.label) == (True, "")
