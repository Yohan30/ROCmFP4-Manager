"""Onglet Bench : tests de performance avec llama-bench."""

import subprocess
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QComboBox, QCheckBox, QPlainTextEdit, QMessageBox,
    QApplication, QGridLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from src.utils.config import Config
from src.core.rocmfpx_manager import ROCmFPXManager


class BenchTab(QWidget):
    """Benchmark intégré avec llama-bench."""

    def __init__(self, config: Config, rocmfpx: ROCmFPXManager):
        super().__init__()
        self.config = config
        self.rocmfpx = rocmfpx
        self._results = []
        self._running = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # === Configuration du bench ===
        config_group = QGroupBox("🏋️ Benchmark Configuration")
        config_grid = QGridLayout(config_group)
        config_grid.setSpacing(8)

        config_grid.addWidget(QLabel("Backend:"), 0, 0)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Vulkan0", "ROCm0", "CPU"])
        config_grid.addWidget(self.backend_combo, 0, 1)

        config_grid.addWidget(QLabel("Prefill (pp):"), 0, 2)
        self.pp_spin = QSpinBox()
        self.pp_spin.setRange(32, 8192)
        self.pp_spin.setSingleStep(32)
        self.pp_spin.setValue(512)
        config_grid.addWidget(self.pp_spin, 0, 3)

        config_grid.addWidget(QLabel("Generate (tg):"), 1, 0)
        self.tg_spin = QSpinBox()
        self.tg_spin.setRange(32, 4096)
        self.tg_spin.setSingleStep(32)
        self.tg_spin.setValue(256)
        config_grid.addWidget(self.tg_spin, 1, 1)

        config_grid.addWidget(QLabel("Number of runs:"), 1, 2)
        self.runs_spin = QSpinBox()
        self.runs_spin.setRange(1, 10)
        self.runs_spin.setValue(3)
        config_grid.addWidget(self.runs_spin, 1, 3)

        self.bench_comparison_check = QCheckBox("Comparative bench (Vulkan + ROCm)")
        config_grid.addWidget(self.bench_comparison_check, 2, 0, 1, 2)

        layout.addWidget(config_group)

        # === Boutons ===
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("🏁 Run Benchmark")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.clicked.connect(self._run_bench)
        btn_layout.addWidget(self.run_btn)

        self.copy_cmd_btn = QPushButton("📋 Copy command")
        self.copy_cmd_btn.clicked.connect(self._copy_command)
        btn_layout.addWidget(self.copy_cmd_btn)

        self.export_csv_btn = QPushButton("📤 Exporter CSV")
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.clicked.connect(self._export_csv)
        btn_layout.addWidget(self.export_csv_btn)

        self.export_json_btn = QPushButton("📤 Exporter JSON")
        self.export_json_btn.setEnabled(False)
        self.export_json_btn.clicked.connect(self._export_json)
        btn_layout.addWidget(self.export_json_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # === Résultats ===
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels([
            "Run", "Backend", "Prefill (t/s)", "Decode (t/s)", "Note"
        ])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        results_layout.addWidget(self.results_table)

        # Stats
        stats_layout = QHBoxLayout()
        self.avg_label = QLabel("Average decode: —")
        stats_layout.addWidget(self.avg_label)
        self.median_label = QLabel("Median decode: —")
        stats_layout.addWidget(self.median_label)
        stats_layout.addStretch()
        results_layout.addLayout(stats_layout)

        layout.addWidget(results_group, 1)

        # === Sortie brute ===
        output_group = QGroupBox("llama-bench raw output")
        output_layout = QVBoxLayout(output_group)
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("monospace", 9))
        self.output_text.document().setMaximumBlockCount(200)
        self.output_text.setMaximumHeight(150)
        output_layout.addWidget(self.output_text)
        layout.addWidget(output_group)

    def _run_bench(self):
        if self._running:
            return
        self._running = True
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ Benchmark running...")
        self.output_text.clear()
        self._results = []

        threading.Thread(target=self._bench_thread, daemon=True).start()

    def _bench_thread(self):
        model_path = self.config.get("last_model", "")
        if not model_path:
            self._notify_error("No model selected in configuration.")
            return

        # Lucebox/DeepSeek V4 models are not supported by llama-bench
        if self.config.is_lucebox_model(model_path):
            self._notify_error(
                "llama-bench cannot benchmark DeepSeek V4 Flash models.\n"
                "These models use the dflash_server runtime (Lucebox), not llama.cpp.\n"
                "Benchmark via the dflash_server directly."
            )
            return

        backends = [self.backend_combo.currentText()]
        if self.bench_comparison_check.isChecked():
            alt = "ROCm0" if backends[0] == "Vulkan0" else "Vulkan0"
            backends.append(alt)

        bench_bin = self.rocmfpx.llama_bench_path
        if not bench_bin:
            self._notify_error("llama-bench not found. Compile ROCmFPX first.")
            return

        pp = self.pp_spin.value()
        tg = self.tg_spin.value()
        runs = self.runs_spin.value()

        all_results = []

        for backend in backends:
            for run_id in range(runs):
                args = [
                    str(bench_bin),
                    "-m", model_path,
                    "-dev", backend,
                    "-ngl", "999",
                    "-fa", "on",
                    "-p", str(pp),
                    "-n", str(tg),
                ]

                self._append_output(f"▶️ Run {run_id+1}/{runs} — Backend: {backend}\n")
                self._append_output(f"   {' '.join(args)}\n")

                try:
                    result = subprocess.run(
                        args, capture_output=True, text=True, timeout=120
                    )
                    output = result.stdout + result.stderr
                    self._append_output(output + "\n")

                    # Parser le résultat
                    pp_speed, tg_speed = self._parse_bench_output(output)
                    all_results.append({
                        "run": run_id + 1,
                        "backend": backend,
                        "pp_speed": pp_speed,
                        "tg_speed": tg_speed,
                    })
                except subprocess.TimeoutExpired:
                    self._append_output("⏰ Timeout\n")
                    all_results.append({
                        "run": run_id + 1,
                        "backend": backend,
                        "pp_speed": 0,
                        "tg_speed": 0,
                    })
                except subprocess.CalledProcessError as e:
                    self._append_output(f"❌ Erreur: {e}\n")

        self._results = all_results
        self._display_results()

        self._running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🏁 Lancer le bench")
        self.export_csv_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)

    def _parse_bench_output(self, output: str):
        """Extrait les vitesses prefill et decode de la sortie de llama-bench."""
        pp_speed = 0.0
        tg_speed = 0.0
        for line in output.split("\n"):
            if "pp" in line and "tg" in line and "|" in line:
                parts = [p.strip() for p in line.split("|")]
                for p in parts:
                    try:
                        val = float(p)
                        if val > 100:  # Prefill speed
                            pp_speed = val
                        elif 0 < val < 500:  # Decode speed
                            tg_speed = val
                    except ValueError:
                        pass
            # Fallback: cherche des motifs
            if "decoding" in line.lower() and "tok/s" in line.lower():
                import re
                matches = re.findall(r"([\d.]+)\s*tok/s", line)
                if matches:
                    tg_speed = float(matches[-1])
        return pp_speed, tg_speed

    def _display_results(self):
        self.results_table.setRowCount(len(self._results))
        for i, r in enumerate(self._results):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(r["run"])))
            self.results_table.setItem(i, 1, QTableWidgetItem(r["backend"]))
            self.results_table.setItem(i, 2,
                QTableWidgetItem(f"{r['pp_speed']:.1f}" if r['pp_speed'] else "—"))
            self.results_table.setItem(i, 3,
                QTableWidgetItem(f"{r['tg_speed']:.1f}" if r['tg_speed'] else "—"))

            if r["tg_speed"] > 0:
                note = "🏆" if r["tg_speed"] > 50 else "⚡" if r["tg_speed"] > 20 else "🐢"
                self.results_table.setItem(i, 4, QTableWidgetItem(note))
            else:
                self.results_table.setItem(i, 4, QTableWidgetItem("❌"))

        # Stats
        tg_speeds = [r["tg_speed"] for r in self._results if r["tg_speed"] > 0]
        if tg_speeds:
            avg = sum(tg_speeds) / len(tg_speeds)
            sorted_s = sorted(tg_speeds)
            median = sorted_s[len(sorted_s) // 2]
            self.avg_label.setText(f"📊 Moyenne decode: {avg:.1f} tok/s")
            self.median_label.setText(f"🎯 Médiane decode: {median:.1f} tok/s")
        else:
            self.avg_label.setText("📊 Moyenne decode: —")
            self.median_label.setText("🎯 Médiane decode: —")

    def _append_output(self, text: str):
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(
            self.output_text, "append",
            Qt.ConnectionType.AutoConnection,
            Q_ARG(str, text)
        )

    def _notify_error(self, msg: str):
        QMetaObject.invokeMethod(
            self, "_show_error",
            Qt.ConnectionType.AutoConnection,
            Q_ARG(str, msg)
        )

    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
        self._running = False
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🏁 Run Benchmark")

    def _copy_command(self):
        model_path = self.config.get("last_model", "")
        if not model_path:
            return
        args = [
            "llama-bench",
            "-m", model_path,
            "-dev", self.backend_combo.currentText(),
            "-ngl", "999",
            "-fa", "on",
            "-p", str(self.pp_spin.value()),
            "-n", str(self.tg_spin.value()),
        ]
        cmd = " ".join(args)
        QApplication.clipboard().setText(cmd)

    def _export_csv(self):
        if not self._results:
            return
        lines = ["run,backend,prefill_tps,decode_tps"]
        for r in self._results:
            lines.append(f"{r['run']},{r['backend']},{r['pp_speed']:.1f},{r['tg_speed']:.1f}")
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter CSV", str(Path.home() / "bench.csv"),
            "CSV (*.csv)"
        )
        if path:
            Path(path).write_text("\n".join(lines))

    def _export_json(self):
        if not self._results:
            return
        import json
        data = {
            "config": {
                "pp": self.pp_spin.value(),
                "tg": self.tg_spin.value(),
                "runs": self.runs_spin.value(),
            },
            "results": self._results,
        }
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter JSON", str(Path.home() / "bench.json"),
            "JSON (*.json)"
        )
        if path:
            Path(path).write_text(json.dumps(data, indent=2))
