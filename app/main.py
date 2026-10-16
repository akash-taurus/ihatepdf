"""ihatepdf desktop app (PySide6). Local-first, drag & drop. Run: python app/main.py"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QTextEdit,
    QSplitter,
    QFormLayout,
    QMessageBox,
    QAbstractItemView,
)

from core import ops

TOOLS = [
    "Merge",
    "Split",
    "Extract pages",
    "Delete pages",
    "Rotate",
    "Reorder",
    "Compress",
    "Images to PDF",
    "PDF to images",
    "Watermark",
    "Page numbers",
    "Encrypt",
    "Decrypt",
    "Info",
]


class Worker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, fn, *a, **kw):
        super().__init__()
        self._fn, self._a, self._kw = fn, a, kw

    def run(self):  # noqa: D102
        try:
            res = self._fn(*self._a, **self._kw)
            if isinstance(res, list):
                res = "\n".join(res)
            self.done.emit(str(res))
        except Exception:
            self.failed.emit(traceback.format_exc(limit=3))


class FileList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDefaultDropAction(Qt.CopyAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p and Path(p).exists():
                self.addItem(p)
        e.acceptProposedAction()


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ihatepdf — local PDF toolkit")
        self.resize(980, 640)
        self._worker: Worker | None = None

        root = QSplitter(Qt.Horizontal)
        self.tools = QListWidget()
        for t in TOOLS:
            QListWidgetItem(t, self.tools)
        self.tools.setCurrentRow(0)
        self.tools.setMaximumWidth(180)
        root.addWidget(self.tools)

        right = QWidget()
        lay = QVBoxLayout(right)

        lay.addWidget(QLabel("Input files (drag & drop supported):"))
        self.files = FileList()
        lay.addWidget(self.files, stretch=3)
        brow = QHBoxLayout()
        self.btn_add = QPushButton("Add files…")
        self.btn_clear = QPushButton("Clear")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_up.setFixedWidth(40)
        self.btn_down.setFixedWidth(40)
        for b in (self.btn_add, self.btn_clear, self.btn_up, self.btn_down):
            brow.addWidget(b)
        brow.addStretch(1)
        lay.addLayout(brow)

        form = QFormLayout()
        self.pages = QLineEdit(placeholderText="e.g. 1,3-5 (blank = all)")
        self.angle = QComboBox()
        self.angle.addItems(["90", "180", "270"])
        self.order = QLineEdit(placeholderText="e.g. 3,1,2")
        self.every = QSpinBox()
        self.every.setRange(0, 1000)
        self.every.setSpecialValueText("—")
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(65)
        self.dpi = QSpinBox()
        self.dpi.setRange(36, 600)
        self.dpi.setValue(150)
        self.text = QLineEdit(placeholderText="Watermark text")
        self.password = QLineEdit(placeholderText="Password", echoMode=QLineEdit.Password)
        self.outfmt = QComboBox()
        self.outfmt.addItems(["png", "jpg"])
        form.addRow("Pages:", self.pages)
        form.addRow("Angle:", self.angle)
        form.addRow("Order:", self.order)
        form.addRow("Split every N:", self.every)
        form.addRow("Image quality:", self.quality)
        form.addRow("DPI:", self.dpi)
        form.addRow("Text:", self.text)
        form.addRow("Password:", self.password)
        form.addRow("Image format:", self.outfmt)
        lay.addLayout(form)

        outrow = QHBoxLayout()
        self.output = QLineEdit(placeholderText="Output file or folder (blank = auto)")
        self.btn_browse = QPushButton("Browse…")
        outrow.addWidget(self.output, stretch=1)
        outrow.addWidget(self.btn_browse)
        lay.addLayout(outrow)

        self.btn_run = QPushButton("Run")
        self.btn_run.setMinimumHeight(40)
        lay.addWidget(self.btn_run)

        lay.addWidget(QLabel("Log:"))
        self.log = QTextEdit(readOnly=True)
        lay.addWidget(self.log, stretch=2)

        root.addWidget(right)
        root.setStretchFactor(1, 1)
        self.setCentralWidget(root)

        self.btn_add.clicked.connect(self._add)
        self.btn_clear.clicked.connect(self.files.clear)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_browse.clicked.connect(self._browse)
        self.btn_run.clicked.connect(self._run)
        self.tools.currentTextChanged.connect(lambda _: self.log.clear())

    # -- helpers
    def _add(self):
        fns, _ = QFileDialog.getOpenFileNames(
            self, "Add files", "", "PDF & images (*.pdf *.png *.jpg *.jpeg)"
        )
        for f in fns:
            self.files.addItem(f)

    def _move(self, d: int):
        r = self.files.currentRow()
        if r < 0:
            return
        nr = r + d
        if 0 <= nr < self.files.count():
            it = self.files.takeItem(r)
            self.files.insertItem(nr, it)
            self.files.setCurrentRow(nr)

    def _inputs(self) -> list[str]:
        return [self.files.item(i).text() for i in range(self.files.count())]

    def _browse(self):
        tool = self.tools.currentItem().text()
        if tool in ("Split", "PDF to images"):
            d = QFileDialog.getExistingDirectory(self, "Output folder")
            if d:
                self.output.setText(d)
        else:
            f, _ = QFileDialog.getSaveFileName(self, "Output", "", "PDF (*.pdf)")
            if f:
                self.output.setText(f)

    def _out(self, default_suffix: str, is_dir: bool = False) -> str:
        v = self.output.text().strip()
        if v:
            return v
        first = self._inputs()[0] if self._inputs() else "output"
        base = Path(first).stem
        tool = self.tools.currentItem().text().lower().replace(" ", "-")
        if is_dir:
            p = Path.cwd() / f"{base}-{tool}"
            p.mkdir(exist_ok=True)
            return str(p)
        return str(Path.cwd() / f"{base}-{tool}{default_suffix}")

    def _run(self):
        tool = self.tools.currentItem().text()
        ins = self._inputs()
        if tool != "Images to PDF" and not ins:
            QMessageBox.warning(self, "ihatepdf", "Add at least one input file.")
            return
        pages = self.pages.text().strip() or None
        try:
            if tool == "Merge":
                self._go(ops.merge, ins, self._out(".pdf"))
            elif tool == "Split":
                every = self.every.value() or None
                self._go(ops.split_pdf, ins[0], self._out("", True), None, every)
            elif tool == "Extract pages":
                self._go(ops.extract_pages, ins[0], pages or "1", self._out(".pdf"))
            elif tool == "Delete pages":
                self._go(ops.delete_pages, ins[0], pages or "1", self._out(".pdf"))
            elif tool == "Rotate":
                self._go(
                    ops.rotate_pages,
                    ins[0],
                    self._out(".pdf"),
                    int(self.angle.currentText()),
                    pages,
                )
            elif tool == "Reorder":
                self._go(
                    ops.reorder_pages, ins[0], self.order.text().strip() or "1", self._out(".pdf")
                )
            elif tool == "Compress":
                self._go(
                    ops.compress_pdf,
                    ins[0],
                    self._out(".pdf"),
                    self.quality.value(),
                    self.dpi.value(),
                )
            elif tool == "Images to PDF":
                self._go(ops.images_to_pdf, ins, self._out(".pdf"))
            elif tool == "PDF to images":
                self._go(
                    ops.pdf_to_images,
                    ins[0],
                    self._out("", True),
                    self.dpi.value(),
                    self.outfmt.currentText(),
                    pages,
                )
            elif tool == "Watermark":
                self._go(
                    ops.watermark_text,
                    ins[0],
                    self._out(".pdf"),
                    self.text.text() or "DRAFT",
                    pages=pages,
                )
            elif tool == "Page numbers":
                self._go(ops.add_page_numbers, ins[0], self._out(".pdf"), pages=pages)
            elif tool == "Encrypt":
                self._go(ops.encrypt_pdf, ins[0], self._out(".pdf"), self.password.text())
            elif tool == "Decrypt":
                self._go(ops.decrypt_pdf, ins[0], self._out(".pdf"), self.password.text())
            elif tool == "Info":
                self._go(ops.info, ins[0])
        except Exception as e:
            self.log.append(f"error: {e}")

    def _go(self, fn, *a, **kw):
        self.btn_run.setEnabled(False)
        self.log.append(f"$ {fn.__name__} …")
        self._worker = Worker(fn, *a, **kw)
        self._worker.done.connect(self._ok)
        self._worker.failed.connect(self._err)
        self._worker.finished.connect(lambda: self.btn_run.setEnabled(True))
        self._worker.start()

    def _ok(self, msg: str):
        self.log.append(msg + "\n✓ done")

    def _err(self, msg: str):
        self.log.append(msg + "\n✗ failed")


def main():
    QApplication.setApplicationName("ihatepdf")
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
