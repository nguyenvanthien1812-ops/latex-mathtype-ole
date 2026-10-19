r"""
gui.py -- Giao dien PyQt6: LaTeX ($...$) -> MathType OLE trong Word.

Chay:  pip install -r requirements.txt
       python gui.py
Can cac file cung thu muc: mtef_encode.py record.py cfb.py latex2mtef.py
                           docx_convert.py render.py
"""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QTextEdit, QFileDialog, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import QThread, pyqtSignal

from docx_convert import convert_docx, reference_template


class Worker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self, src, dst, ref):
        super().__init__()
        self.src, self.dst, self.ref = src, dst, ref

    def run(self):
        try:
            template = None
            if self.ref:
                self.log.emit(f"Nap vo OLE tu file mau: {self.ref}")
                template = reference_template(self.ref)
                self.log.emit(f"  CLSID: {template.get('clsid_str')}")
            self.log.emit(f"Mo: {self.src}")
            stats = convert_docx(self.src, self.dst, log=self.log.emit, template=template)
            self.done.emit(stats)
        except Exception:
            self.fail.emit(traceback.format_exc())


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LaTeX ($...$) -> MathType OLE  |  Word converter")
        self.resize(700, 500)
        self.worker = None
        self._build()

    def _row(self, label, placeholder, btn_text, slot):
        row = QHBoxLayout()
        edit = QLineEdit(); edit.setPlaceholderText(placeholder)
        b = QPushButton(btn_text); b.clicked.connect(slot)
        row.addWidget(QLabel(label)); row.addWidget(edit, 1); row.addWidget(b)
        return row, edit

    def _build(self):
        root = QVBoxLayout(self)
        r1, self.in_edit  = self._row("Đầu vào: ", "Chọn file .docx đầu vào...",
                                      "Chọn file Word...", self.pick_in)
        r2, self.out_edit = self._row("Đầu ra:  ", "File .docx đầu ra...",
                                      "Lưu thành...", self.pick_out)
        r3, self.ref_edit = self._row("MathType mẫu:", "(NÊN CÓ) 1 file .docx có công thức MathType...",
                                      "Chọn file mẫu...", self.pick_ref)
        root.addLayout(r1); root.addLayout(r2); root.addLayout(r3)

        hint = QLabel("File mẫu = một công thức bạn tự gõ bằng MathType. Dùng để Word "
                      "nhận đúng là MathType (tránh lỗi 'Equation Editor 3.0').")
        hint.setStyleSheet("color:#555;"); hint.setWordWrap(True)
        root.addWidget(hint)

        self.btn = QPushButton("Chuyển đổi")
        self.btn.setStyleSheet("font-weight:bold; padding:8px;")
        self.btn.clicked.connect(self.run_convert)
        root.addWidget(self.btn)

        self.bar = QProgressBar(); self.bar.setRange(0, 0); self.bar.hide()
        root.addWidget(self.bar)
        root.addWidget(QLabel("Nhật ký:"))
        self.log = QTextEdit(); self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

    def pick_in(self):
        p, _ = QFileDialog.getOpenFileName(self, "Chọn file Word", "", "Word (*.docx)")
        if p:
            self.in_edit.setText(p)
            if not self.out_edit.text():
                base, ext = os.path.splitext(p)
                self.out_edit.setText(base + "_mathtype" + ext)

    def pick_out(self):
        p, _ = QFileDialog.getSaveFileName(self, "Lưu file ra", "", "Word (*.docx)")
        if p: self.out_edit.setText(p)

    def pick_ref(self):
        p, _ = QFileDialog.getOpenFileName(self, "Chọn file MathType mẫu", "",
                                           "Word/OLE (*.docx *.bin)")
        if p: self.ref_edit.setText(p)

    def run_convert(self):
        src = self.in_edit.text().strip(); dst = self.out_edit.text().strip()
        ref = self.ref_edit.text().strip() or None
        if not src or not os.path.isfile(src):
            QMessageBox.warning(self, "Thiếu file", "Chưa chọn file Word hợp lệ."); return
        if not dst:
            QMessageBox.warning(self, "Thiếu đầu ra", "Chưa chọn nơi lưu file."); return
        if os.path.abspath(src) == os.path.abspath(dst):
            QMessageBox.warning(self, "Trùng file", "File ra phải khác file gốc."); return
        if ref and not os.path.isfile(ref):
            QMessageBox.warning(self, "Thiếu file mẫu", "File MathType mẫu không tồn tại."); return

        self.log.clear(); self.btn.setEnabled(False); self.bar.show()
        self.worker = Worker(src, dst, ref)
        self.worker.log.connect(self.log.append)
        self.worker.done.connect(self._done)
        self.worker.fail.connect(self._fail)
        self.worker.start()

    def _done(self, stats):
        self.bar.hide(); self.btn.setEnabled(True)
        self.log.append(f"\nXong. Đã chuyển {stats['converted']} công thức, "
                        f"bỏ qua {stats['failed']}.")
        QMessageBox.information(self, "Hoàn tất",
            f"Đã chuyển {stats['converted']} công thức.\nBỏ qua: {stats['failed']}.\n"
            f"File: {self.out_edit.text()}")

    def _fail(self, tb):
        self.bar.hide(); self.btn.setEnabled(True)
        self.log.append("LỖI:\n" + tb)
        QMessageBox.critical(self, "Lỗi", tb.splitlines()[-1] if tb else "Lỗi không xác định")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())
