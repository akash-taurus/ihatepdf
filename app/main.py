"""ihatepdf desktop app (PySide6). Local-first, drag & drop.

Run:  python app/main.py
The window is a thin shell: tool definitions live in ``app/tools.py`` and all
the actual work happens in ``core``. Only the fields a given tool needs are
shown, so the form stays short no matter how many tools exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.thumbnails import ThumbnailPane
from app.tools import TOOLS as TOOL_SPECS
from app.tools import Ctx, Tool, unavailable_tools
from app.worker import Worker, format_result
from core import __version__, convert

#: Field id -> (label, kind, extra). Kind drives the widget that gets built.
FIELD_DEFS: dict[str, tuple[str, str, object]] = {
    "pages": ("Pages", "line", "e.g. 1,3-5 (blank = all pages)"),
    "ranges": ("Split ranges", "line", 'e.g. "1-2,3-5"'),
    "every": ("Split every N pages", "spin", (0, 1000, 0)),
    "angle": ("Angle (clockwise)", "combo", ["90", "180", "270"]),
    "order": ("Page order", "line", "e.g. 3,1,2"),
    "quality": ("Image quality", "spin", (1, 100, 65)),
    "dpi": ("DPI", "spin", (36, 600, 150)),
    "format": ("Image format", "combo", ["png", "jpg"]),
    "text": ("Watermark text", "line", "CONFIDENTIAL"),
    "fontsize": ("Font size", "spin", (6, 300, 48)),
    "opacity": ("Opacity (0-1]", "dbl", (0.05, 1.0, 0.25, 2)),
    "password": ("Password", "password", None),
    "language": ("OCR languages", "line", "eng, or eng+deu"),
    "engine": ("DOCX engine", "combo", ["auto", "libreoffice", "builtin"]),
    "force": ("Re-OCR pages that already have text", "check", None),
    "flatten": ("Bake values in and drop the form", "check", None),
    "values": (
        "Field values",
        "text",
        "Plain PDF form:\nname=value per line, e.g.\nfull_name=Ada Lovelace\nagree=yes",
    ),
    "fields": (
        "Field JSON",
        "text",
        '[{"name": "full_name", "type": "text", "rect": [72, 500, 300, 520], "value": ""}]',
    ),
    "pfx": ("Certificate (.p12/.pfx)", "open", "Certificates (*.p12 *.pfx);;All files (*)"),
    "pfx_password": ("Certificate password", "password", None),
    "reason": ("Reason", "line", "Approval"),
    "location": ("Location", "line", "Pune"),
    "page": ("Page", "spin", (1, 100000, 1)),
    "box": ("Signature box", "line", "x0,y0,x1,y1 from the page's top-left"),
    "image": ("Image", "open", "Images (*.png *.jpg *.jpeg);;All files (*)"),
    "width": ("Width (points)", "line", "160"),
    "x": ("X (points, blank = right edge)", "line", "auto"),
    "y": ("Y (points, blank = bottom edge)", "line", "auto"),
}

#: Default file extension and label for each tool output kind.
OUTPUT_KINDS = {
    "file": (".pdf", "Output file", "PDF (*.pdf)"),
    "docx": (".docx", "Output file", "Word (*.docx)"),
    "txt": (".txt", "Text file (blank = log only)", "Text (*.txt)"),
    "dir": ("", "Output folder", None),
}


class FileList(QListWidget):
    """Input file list that accepts dropped files and folders."""

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDefaultDropAction(Qt.CopyAction)

    def dragEnterEvent(self, event) -> None:  # noqa: D102
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: D102
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: D102
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls()])
        event.acceptProposedAction()

    def add_paths(self, paths: list[str]) -> None:
        for path in paths:
            item = Path(path)
            if not path:
                continue
            if item.is_dir():
                for child in sorted(item.iterdir()):
                    if child.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"):
                        self.addItem(str(child))
            elif item.exists():
                self.addItem(str(item))


class Main(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"ihatepdf {__version__} — local PDF toolkit")
        self.resize(1080, 720)
        self._worker: Worker | None = None
        #: field id -> (widget, getter); created once, reused by every tool
        self._fields: dict[str, tuple[QWidget, object]] = {}
        #: field id -> form row index, for showing/hiding rows per tool
        self._rows: dict[str, int] = {}
        #: field ids currently on screen for the selected tool
        self._visible: tuple[str, ...] = ()
        self._missing = unavailable_tools()

        root = QSplitter(Qt.Horizontal)
        root.addWidget(self._build_tool_panel())
        root.addWidget(self._build_work_area())
        root.setStretchFactor(1, 1)
        self.setCentralWidget(root)

        self.tools.currentRowChanged.connect(self._tool_changed)
        self.tools.setCurrentRow(0)
        self._log_capabilities()

    # ---------------------------------------------------------------- panels

    def _build_tool_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Tool"))

        self.filter = QLineEdit(placeholderText="Filter tools…")
        layout.addWidget(self.filter)

        self.tools = QListWidget()
        for spec in TOOL_SPECS:
            label = f"⚠ {spec.label}" if spec.label in self._missing else spec.label
            item = QListWidgetItem(label, self.tools)
            if spec.label in self._missing:
                item.setToolTip(self._missing[spec.label])
            elif spec.hint:
                item.setToolTip(spec.hint)
        self.tools.setMaximumWidth(220)
        layout.addWidget(self.tools, stretch=1)
        self.filter.textChanged.connect(self._apply_filter)
        return panel

    def _build_work_area(self) -> QWidget:
        self.tabs = QTabWidget()

        # --- tab 1: files, options, log
        page = QWidget()
        layout = QVBoxLayout(page)

        self.tool_hint = QLabel()
        self.tool_hint.setWordWrap(True)
        layout.addWidget(self.tool_hint)

        layout.addWidget(QLabel("Input files (drag & drop, or paste paths):"))
        self.files = FileList()
        self.files.setAcceptDrops(True)
        self.files.setDragDropMode(QAbstractItemView.DropOnly)
        layout.addWidget(self.files, stretch=2)

        rows = QHBoxLayout()
        for text, slot in (
            ("Add files…", self._add_files),
            ("Clear", self.files.clear),
            ("↑", lambda: self._move_file(-1)),
            ("↓", lambda: self._move_file(1)),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            if text in ("↑", "↓"):
                button.setFixedWidth(40)
            rows.addWidget(button)
        rows.addStretch(1)
        layout.addLayout(rows)

        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._build_all_fields()
        layout.addWidget(self.form_host)

        out_row = QHBoxLayout()
        self.out_label = QLabel("Output file")
        self.output = QLineEdit(placeholderText="blank = auto-named next to the input")
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse_output)
        out_row.addWidget(self.out_label)
        out_row.addWidget(self.output, stretch=1)
        out_row.addWidget(self.btn_browse)
        layout.addLayout(out_row)

        run_row = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_run.setMinimumHeight(38)
        self.btn_run.clicked.connect(self._run)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        run_row.addWidget(self.btn_run, stretch=2)
        run_row.addWidget(self.progress, stretch=1)
        layout.addLayout(run_row)

        log_row = QHBoxLayout()
        log_row.addWidget(QLabel("Log"))
        log_row.addStretch(1)
        clear = QPushButton("Clear log")
        clear.clicked.connect(lambda: self.log.clear())
        log_row.addWidget(clear)
        layout.addLayout(log_row)

        self.log = QTextEdit(readOnly=True)
        self.log.setPlaceholderText("Results appear here.")
        layout.addWidget(self.log, stretch=3)
        self.tabs.addTab(page, "Files & options")

        # --- tab 2: page thumbnails
        self.thumbs = ThumbnailPane()
        self.thumbs.status.connect(self._append)
        self.tabs.addTab(self.thumbs, "Page order (thumbnails)")
        return self.tabs

    # ---------------------------------------------------------------- fields

    def _make_widget(self, field_id: str) -> tuple[str, QWidget, object]:
        label, kind, extra = FIELD_DEFS[field_id]
        widget: QWidget
        if kind == "line":
            widget = QLineEdit(placeholderText=str(extra or ""))
            getter = lambda w=widget: w.text()  # noqa: E731
        elif kind == "password":
            widget = QLineEdit(echoMode=QLineEdit.Password)
            getter = lambda w=widget: w.text()  # noqa: E731
        elif kind == "spin":
            low, high, default = extra  # type: ignore[misc]
            widget = QSpinBox()
            widget.setRange(int(low), int(high))
            widget.setValue(int(default))
            widget.setSpecialValueText("—")
            getter = lambda w=widget: w.value()  # noqa: E731
        elif kind == "dbl":
            low, high, default, decimals = extra  # type: ignore[misc]
            widget = QDoubleSpinBox()
            widget.setRange(float(low), float(high))
            widget.setDecimals(int(decimals))
            widget.setSingleStep(0.05)
            widget.setValue(float(default))
            getter = lambda w=widget: w.value()  # noqa: E731
        elif kind == "combo":
            widget = QComboBox()
            widget.addItems([str(option) for option in extra])  # type: ignore[arg-type]
            getter = lambda w=widget: w.currentText()  # noqa: E731
        elif kind == "check":
            widget = QCheckBox()
            getter = lambda w=widget: w.isChecked()  # noqa: E731
        elif kind == "text":
            widget = QPlainTextEdit()
            widget.setPlaceholderText(str(extra or ""))
            widget.setFixedHeight(90)
            getter = lambda w=widget: w.toPlainText()  # noqa: E731
        else:  # "open": a line edit paired with a browse button
            widget = QLineEdit(placeholderText="blank to browse")
            getter = lambda w=widget: w.text()  # noqa: E731
        return label, widget, getter

    def _build_all_fields(self) -> None:
        """Create every option widget once; tools then just show the ones they use.

        Rows are hidden rather than rebuilt so that anything already typed
        survives switching tools, and so no widget is ever destroyed while a
        reference to it is held.
        """
        for field_id, (label, kind, _extra) in FIELD_DEFS.items():
            _, widget, getter = self._make_widget(field_id)
            self._fields[field_id] = (widget, getter)
            if kind == "open":
                holder = QWidget()
                row = QHBoxLayout(holder)
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(widget, stretch=1)
                button = QPushButton("Browse…")
                button.clicked.connect(lambda _=False, fid=field_id: self._browse_field(fid))
                row.addWidget(button)
                self.form.addRow(label, holder)
            else:
                self.form.addRow(label, widget)
            self._rows[field_id] = self.form.rowCount() - 1
            self.form.setRowVisible(self._rows[field_id], False)

    def _rebuild_form(self, tool: Tool) -> None:
        wanted = set(tool.fields)
        for field_id, row in self._rows.items():
            self.form.setRowVisible(row, field_id in wanted)
        self._visible = tuple(field_id for field_id in FIELD_DEFS if field_id in wanted)

    def visible_fields(self) -> tuple[str, ...]:
        """Option fields currently shown, in form order (used by the tests too)."""
        return self._visible

    def _values(self) -> dict:
        return {fid: getter(widget) for fid, (widget, getter) in self._fields.items()}

    def _browse_field(self, field_id: str) -> None:
        widget, _ = self._fields[field_id]
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a file", "", str(FIELD_DEFS[field_id][2] or "All files (*)")
        )
        if path:
            widget.setText(path)  # type: ignore[attr-defined]

    # ---------------------------------------------------------------- actions

    def current_tool(self) -> Tool:
        return TOOL_SPECS[self.tools.currentRow()]

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row, spec in enumerate(TOOL_SPECS):
            self.tools.item(row).setHidden(bool(needle) and needle not in spec.label.lower())

    def _tool_changed(self, row: int) -> None:
        if row < 0:
            return
        tool = TOOL_SPECS[row]
        self._rebuild_form(tool)

        warnings = []
        if tool.label in self._missing:
            warnings.append(f"⚠ {self._missing[tool.label]}")
        if tool.hint:
            warnings.append(tool.hint)
        self.tool_hint.setText("  ".join(warnings))
        self.tool_hint.setVisible(bool(warnings))

        if tool.output == "none":
            self.out_label.setVisible(False)
            self.output.setVisible(False)
            self.btn_browse.setVisible(False)
        else:
            _, label, _ = OUTPUT_KINDS.get(tool.output, OUTPUT_KINDS["file"])
            self.out_label.setText(label)
            self.output.setVisible(True)
            self.out_label.setVisible(True)
            self.output.setPlaceholderText(
                "blank = output goes next to the input file"
                if tool.output != "txt"
                else "blank = show the text in the log"
            )
            self.btn_browse.setVisible(True)
        if tool.label == "Reorder pages" and self.thumbs.list.count():
            self._append("Using the page order from the thumbnails tab.")

    def _add_files(self) -> None:
        tool = self.current_tool()
        filters = (
            "Images (*.png *.jpg *.jpeg)"
            if tool.label == "Images to PDF"
            else "PDF & images (*.pdf *.png *.jpg *.jpeg)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "Add files", "", filters)
        self.files.add_paths(paths)

    def _move_file(self, delta: int) -> None:
        row = self.files.currentRow()
        if row < 0:
            return
        target = row + delta
        if 0 <= target < self.files.count():
            item = self.files.takeItem(row)
            self.files.insertItem(target, item)
            self.files.setCurrentRow(target)

    def _inputs(self) -> list[str]:
        return [self.files.item(i).text() for i in range(self.files.count())]

    def _browse_output(self) -> None:
        tool = self.current_tool()
        if tool.output == "dir":
            path = QFileDialog.getExistingDirectory(self, "Output folder")
        elif tool.output == "txt":
            path, _ = QFileDialog.getSaveFileName(self, "Text output", "", "Text (*.txt)")
        elif tool.output == "docx":
            path, _ = QFileDialog.getSaveFileName(self, "Output", "", "Word (*.docx)")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Output", "", "PDF (*.pdf)")
        if path:
            self.output.setText(path)

    def _auto_output(self, tool: Tool) -> str | None:
        suffix, _, _ = OUTPUT_KINDS.get(tool.output, OUTPUT_KINDS["file"])
        inputs = self._inputs()
        stem = Path(inputs[0]).stem if inputs else "output"
        slug = tool.label.lower().replace(" ", "-").replace("/", "-")
        if tool.output == "dir":
            target = Path.cwd() / f"{stem}-{slug}"
            target.mkdir(exist_ok=True)
            return str(target)
        return str(Path.cwd() / f"{stem}-{slug}{suffix}")

    def _run(self) -> None:
        tool = self.current_tool()
        inputs = self._inputs()
        if not inputs:
            QMessageBox.warning(self, "ihatepdf", "Add at least one input file.")
            return

        if tool.output == "none":
            out = None
        else:
            typed = self.output.text().strip()
            if typed:
                out = typed
            elif tool.output == "txt":
                out = None  # txt tools fall back to the log pane
            else:
                out = self._auto_output(tool)

        values = self._values()
        order = self.thumbs.order() if tool.label == "Reorder pages" else None
        ctx = Ctx(inputs=inputs, out=out, values=values, order=order or None)

        self.btn_run.setEnabled(False)
        self.progress.setRange(0, 0)  # indeterminate while the job runs
        self._append(f"$ {tool.label} …")
        self._worker = Worker(tool.run, ctx)
        self._worker.done.connect(self._succeeded)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _succeeded(self, result) -> None:
        if result is None:
            self._append("✓ done (nothing to report)")
            return
        self._append(format_result(result) + "\n✓ done")

    def _failed(self, traceback_text: str) -> None:
        self._append(traceback_text.strip() + "\n✗ failed")

    def _finished(self) -> None:
        self.btn_run.setEnabled(True)
        self.progress.setRange(0, 100)  # back to determinate; no job in flight
        self.progress.setValue(0)

    # ---------------------------------------------------------------- logging

    def _append(self, message: str) -> None:
        self.log.append(message)

    def _log_capabilities(self) -> None:
        caps = convert.capabilities()
        self._append(f"ihatepdf {__version__} — everything runs locally, nothing is uploaded.")
        self._append(
            "Backends: "
            f"PyMuPDF {caps['pymupdf']}, "
            f"LibreOffice {'available' if caps['libreoffice'] else 'not installed'}, "
            f"Tesseract {'available' if caps['tesseract'] else 'not installed'}, "
            f"built-in DOCX writer available."
        )
        for label, reason in self._missing.items():
            self._append(f"⚠ {label}: {reason}")
        self._append("")


def main() -> None:
    QApplication.setApplicationName("ihatepdf")
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
