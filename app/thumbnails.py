"""Page-thumbnail pane: drag pages into the order you want.

Thumbnails render on a worker thread and stream in one by one, so opening a
300-page document does not freeze the window. The order shown here can be
applied with one button, or reused by the "Reorder pages" tool.
"""

from __future__ import annotations

from pathlib import Path

import fitz
from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import ops

#: Longest edge of a rendered thumbnail, in pixels.
THUMB_PX = 110

#: Rendering every page of a huge document up front is wasteful; cap the preview.
MAX_PAGES = 500


class ThumbRender(QThread):
    """Render page thumbnails one at a time and emit them as they finish."""

    rendered = Signal(int, QImage)
    failed = Signal(str)
    finished_all = Signal(int)

    def __init__(self, pdf_path: str, thumb_px: int = THUMB_PX) -> None:
        super().__init__()
        self._path = pdf_path
        self._px = thumb_px
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D102 - QThread entry point
        count = 0
        try:
            with fitz.open(self._path) as doc:
                count = min(doc.page_count, MAX_PAGES)
                for pno in range(count):
                    if self._cancelled:
                        break
                    page = doc[pno]
                    longest = max(page.rect.width, page.rect.height) or 1.0
                    zoom = max(0.05, min(self._px / longest, 4.0))
                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False
                    )
                    image = QImage(
                        pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
                    ).copy()
                    self.rendered.emit(pno, image)
        except Exception as exc:
            self.failed.emit(str(exc))
        self.finished_all.emit(count)


class ThumbnailPane(QWidget):
    """List of page thumbnails with drag & drop, plus explicit move buttons."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: str | None = None
        self._renderer: ThumbRender | None = None

        layout = QVBoxLayout(self)
        self.header = QLabel("Load a PDF to arrange its pages.")
        self.header.setWordWrap(True)
        layout.addWidget(self.header)

        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(QSize(THUMB_PX, THUMB_PX * 1.45))
        self.list.setResizeMode(QListView.Adjust)
        self.list.setFlow(QListView.LeftToRight)
        self.list.setWrapping(True)
        self.list.setMovement(QListView.Static)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(6)
        layout.addWidget(self.list, stretch=1)

        buttons = QHBoxLayout()
        self.btn_load = QPushButton("Load pages")
        self.btn_left = QPushButton("Move ◀")
        self.btn_right = QPushButton("Move ▶")
        self.btn_reverse = QPushButton("Reverse")
        self.btn_reset = QPushButton("Reset order")
        self.btn_save = QPushButton("Save reordered PDF…")
        for button in (
            self.btn_load,
            self.btn_left,
            self.btn_right,
            self.btn_reverse,
            self.btn_reset,
            self.btn_save,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.btn_load.clicked.connect(self.load_dialog)
        self.btn_left.clicked.connect(lambda: self.move_selection(-1))
        self.btn_right.clicked.connect(lambda: self.move_selection(1))
        self.btn_reverse.clicked.connect(self.reverse)
        self.btn_reset.clicked.connect(self.reset_order)
        self.btn_save.clicked.connect(lambda: self.save_reordered(None))

    # -- loading

    def shutdown(self) -> None:
        """Stop the render thread. Safe to call repeatedly or from closeEvent.

        A QThread that is destroyed while still running aborts the process, so
        the pane always parks its renderer before going away.
        """
        renderer = self._renderer
        self._renderer = None
        if renderer is not None:
            renderer.cancel()
            renderer.wait(3000)

    def closeEvent(self, event) -> None:  # noqa: D102 - Qt override
        self.shutdown()
        super().closeEvent(event)

    def load_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a PDF", "", "PDF (*.pdf)")
        if path:
            self.load(path)

    def load(self, pdf_path: str) -> None:
        """Render thumbnails for ``pdf_path`` (cancel any render in flight)."""
        if not Path(pdf_path).exists():
            self.status.emit(f"No such file: {pdf_path}")
            return
        self.shutdown()
        self.list.clear()
        self._source = pdf_path
        self.header.setText(f"Page order for {Path(pdf_path).name} (drag to rearrange):")

        self._renderer = ThumbRender(pdf_path)
        self._renderer.rendered.connect(self._add_thumbnail)
        self._renderer.failed.connect(lambda msg: self.status.emit(f"Thumbnail error: {msg}"))
        self._renderer.finished_all.connect(self._render_finished)
        self._renderer.start()

    def _add_thumbnail(self, page_index: int, image: QImage) -> None:
        item = QListWidgetItem(QIcon(QPixmap.fromImage(image)), f"p{page_index + 1}")
        item.setData(Qt.UserRole, page_index)
        item.setTextAlignment(Qt.AlignHCenter)
        item.setToolTip(f"Original page {page_index + 1}")
        self.list.addItem(item)

    def _render_finished(self, count: int) -> None:
        if count >= MAX_PAGES:
            self.status.emit(f"Showing the first {MAX_PAGES} pages only.")
        else:
            self.status.emit(
                f"Loaded {count} page thumbnail(s) from {Path(self._source or '').name}"
            )

    # -- reordering

    def order(self) -> list[int]:
        """Original 1-based page numbers, in the order currently displayed."""
        return [int(self.list.item(i).data(Qt.UserRole)) + 1 for i in range(self.list.count())]

    def set_order(self, pages: list[int]) -> None:
        """Arrange existing items to match ``pages`` (1-based, same members)."""
        by_page: dict[int, QListWidgetItem] = {}
        while self.list.count():
            item = self.list.takeItem(0)
            by_page[int(item.data(Qt.UserRole)) + 1] = item
        for page in pages:
            item = by_page.get(page)
            if item is not None:
                self.list.addItem(item)

    def move_selection(self, delta: int) -> None:
        rows = sorted(index.row() for index in self.list.selectedIndexes())
        if not rows:
            self.status.emit("Select one or more thumbnails to move")
            return
        if delta < 0:
            if rows[0] == 0:
                return
            for row in rows:
                item = self.list.takeItem(row)
                self.list.insertItem(row + delta, item)
                item.setSelected(True)
        else:
            if rows[-1] == self.list.count() - 1:
                return
            for row in reversed(rows):
                item = self.list.takeItem(row)
                self.list.insertItem(row + delta, item)
                item.setSelected(True)

    def reverse(self) -> None:
        pages = list(reversed(self.order()))
        self.set_order(pages)
        self.status.emit("Reversed page order")

    def reset_order(self) -> None:
        if not self.list.count():
            return
        self.set_order(sorted(self.order()))
        self.status.emit("Reset to the original page order")

    # -- applying

    def save_reordered(self, output_path: str | None = None) -> str | None:
        if not self._source:
            self.status.emit("Load a PDF first")
            return None
        if self.list.count() == 0:
            return None
        source = Path(self._source)
        target = output_path
        if target is None:
            target, _ = QFileDialog.getSaveFileName(
                self,
                "Save reordered PDF",
                str(source.with_name(f"{source.stem}-reordered.pdf")),
                "PDF (*.pdf)",
            )
            if not target:
                return None
        try:
            result = ops.reorder_pages(self._source, ",".join(str(p) for p in self.order()), target)
        except Exception as exc:
            QMessageBox.warning(self, "ihatepdf", str(exc))
            self.status.emit(f"error: {exc}")
            return None
        self.status.emit(f"Saved reordered PDF: {result}")
        return result
