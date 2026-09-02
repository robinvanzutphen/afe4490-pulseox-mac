r"""
Live PPG viewer for the AFE4400/AFE4490 SpO2 EVM -- direct USB serial.

Streams IR and Red PPG at the full pulse-repetition rate (~500 Hz) straight from
the board's serial port -- no TI GUI, supported Python 3.

Two tabs:
  * Acquisition -- scrolling live PPG (time axis), Start/Stop, Continuous or Finite
    (N-second) capture, Remove-DC toggle, LED-current sliders, and Save waveform.
  * Analysis    -- a visual ratio-of-ratios walkthrough, selectable Beer-Lambert
    or custom calibration mapping, and live heart-rate spectrum.

USAGE  (close the TI GUI/serial terminals first -- the port is exclusive):
    python live_viewer.py
    python live_viewer.py COM4
"""
import os
import sys
import csv
import time
import queue
from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets
from serial.tools import list_ports

from afe.serial_link import AFESerial, AFESerialError, CHANNELS
from afe.signal_processing import bandpass_fft, peak_count_rate

PORT_DEFAULT = "COM4"
TI_USB_VID = 0x2047
TI_USB_PID = 0x0300
N_STREAM = 100000000            # effectively continuous; auto-restarts if it ends
WINDOW_SECONDS = 8              # scrolling display window
ANALYSIS_MAX_SECONDS = 30       # longest analysis window kept in the buffer
HR_WIN_DEFAULT = 8             # seconds used to compute HR   (user-adjustable)
SPO2_WIN_DEFAULT = 8          # seconds used to compute SpO2 (user-adjustable)
HR_TREND_SECONDS = 60         # scrolling span of the HR-vs-time plot
RECORD_MAX_SECONDS = 20 * 60    # cap on retained samples (memory bound)
FS_NOMINAL = 500
EMA_ALPHA = 0.02                # DC tracker for the AC (Remove-DC) view

# Heart-rate estimation
HR_MIN_HZ, HR_MAX_HZ = 0.7, 3.5     # search band (42-210 bpm)
HR_PAD_LEN = 1 << 15                # FFT zero-pad length -> smooth spectrum, fine peak
HR_CONF_MIN = 3.0                   # peak-to-median prominence needed to accept an update
HR_SMOOTH = 5                       # median over the last N accepted estimates
SPEC_EMA = 0.3                      # frame-to-frame smoothing of the HR spectrum plot

# SpO2 modulation waveforms -- updated every display frame (~30 ms), so they
# scroll smoothly instead of jumping on the slow analysis timer.
MOD_WINDOW_SECONDS = 6
A_MOD_LP = 1.0 - np.exp(-2.0 * np.pi * 6.0 / FS_NOMINAL)   # ~6 Hz smoothing
A_MOD_HP = 1.0 - np.exp(-2.0 * np.pi * 0.5 / FS_NOMINAL)   # ~0.5 Hz baseline (DC) tracker

IDX_IR = CHANNELS.index("LED1-ALED1VAL")   # IR, ambient-subtracted (hardware)
IDX_RED = CHANNELS.index("LED2-ALED2VAL")  # Red, ambient-subtracted (hardware)
IDX_ALED1 = CHANNELS.index("ALED1VAL")     # IR-slot ambient (background)
IDX_ALED2 = CHANNELS.index("ALED2VAL")     # Red-slot ambient (background)
DISP_KEYS = ("ir", "red", "ir_amb", "red_amb")

# palette -- soft, high-contrast on a white plot canvas
COL_IR = "#2a6f97"     # IR trace / blue accent
COL_RED = "#d1495b"    # Red trace / red accent
COL_AMB = "#9aa0a8"    # ambient / background trace
COL_AXIS = "#c9ced6"
COL_TEXT = "#5a616b"
COL_CURVE = "#7a828c"
IR_PEN = pg.mkPen(COL_IR, width=1.8)
RED_PEN = pg.mkPen(COL_RED, width=1.8)
AMB_PEN = pg.mkPen(COL_AMB, width=1.0, style=QtCore.Qt.DashLine)

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", COL_TEXT)
pg.setConfigOptions(antialias=True)

STYLE = """
* { font-family:"Segoe UI","Segoe UI Variable Text",Arial; font-size:10pt; color:#2b2f36; }
QMainWindow { background:#eef1f5; }
QTabWidget::pane { border:1px solid #d9dce1; border-radius:8px; background:#ffffff; top:-1px; }
QTabBar::tab { background:#e2e6ec; color:#565d66; min-width:170px; padding:9px 24px; margin-right:4px;
               border-top-left-radius:7px; border-top-right-radius:7px; }
QTabBar::tab:selected { background:#ffffff; color:#1f2329; font-weight:600; }
QGroupBox { font-weight:600; border:1px solid #dfe3e8; border-radius:9px;
            margin-top:12px; padding:12px 10px 10px 10px; background:#ffffff; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#3a4048; }
QPushButton { background:#eef1f5; border:1px solid #cfd4da; border-radius:6px; padding:6px 12px; }
QPushButton:hover { background:#e4e9ef; }
QPushButton#start { background:#2a6f97; color:#ffffff; border:none; font-weight:700; padding:9px; }
QPushButton#start:hover { background:#265f81; }
QPushButton#start:checked { background:#d1495b; }
QComboBox, QSpinBox, QDoubleSpinBox { background:#ffffff; border:1px solid #cfd4da;
            border-radius:5px; padding:3px 6px; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border:1px solid #2a6f97; }
QCheckBox, QRadioButton { spacing:6px; }
QStatusBar { background:#e2e6ec; }
QStatusBar QLabel { color:#4a5058; }
QLabel#hr { font-size:46px; font-weight:800; color:#d1495b; }
QLabel#spo2 { font-size:46px; font-weight:800; color:#2a6f97; }
QLabel#equation { font-family:Consolas,"Cascadia Mono",monospace; font-size:11pt; color:#3a4048; }
QLabel#qualityGood { color:#1f8a4c; font-weight:600; }
QLabel#qualityWait { color:#b06a12; font-weight:600; }
QLabel[class~="mono"] { font-family:Consolas,"Cascadia Mono",monospace; }
"""


# Prahl haemoglobin spectra, commonly used teaching values at the nominal LED
# wavelengths.  Units cancel in the saturation equation as long as all four
# coefficients use the same units.
EPS_HBO2_RED = 319.6       # HbO2 at 660 nm
EPS_HB_RED = 3226.56       # Hb   at 660 nm
EPS_HBO2_IR = 1214.0       # HbO2 at 940 nm
EPS_HB_IR = 693.44         # Hb   at 940 nm


def spo2_beer_lambert(R, eps_hbo2_red=EPS_HBO2_RED, eps_hb_red=EPS_HB_RED,
                      eps_hbo2_ir=EPS_HBO2_IR, eps_hb_ir=EPS_HB_IR,
                      path_ratio=1.0):
    """Ideal two-species Beer-Lambert solution for fractional saturation.

    R is delta-A_red / delta-A_ir (approximated by the familiar AC/DC ratio),
    and path_ratio is L_red/L_ir.  Real tissue scatters, so this is deliberately
    presented in the UI as an ideal model rather than a clinical calibration.
    """
    q = np.asarray(R, dtype=float) / path_ratio
    numerator = eps_hb_red - q * eps_hb_ir
    denominator = (q * (eps_hbo2_ir - eps_hb_ir)
                   - (eps_hbo2_red - eps_hb_red))
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * numerator / denominator


# --------------------------------------------------------------------------- #
#  Acquisition thread                                                         #
# --------------------------------------------------------------------------- #
class StreamWorker(QtCore.QThread):
    """Owns the serial link. Streams 6-channel samples into a queue when running.
    Start/Stop and LED changes are posted as commands and serviced between packets."""

    connected = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, port, out_queue):
        super().__init__()
        self.port = port
        self.q = out_queue
        self.dev = None
        self._cmds = queue.Queue()
        self._running = True
        self._streaming = False

    def post(self, cmd):
        self._cmds.put(cmd)

    def stop(self):
        self._running = False

    def run(self):
        try:
            self.dev = AFESerial(self.port, timeout=1.0)
            idn = self.dev.device_id()
            maj, mn = self.dev.firmware_revision()
            self.dev.reset_link()
            self.dev.configure_evm_defaults()
            self.connected.emit("%s   fw %d.%d" % (idn, maj, mn))
        except Exception as e:              # serial + protocol errors
            self.failed.emit(str(e))
            return

        while self._running:
            try:
                while True:
                    self._handle(self._cmds.get_nowait())
            except queue.Empty:
                pass

            if not self._streaming:
                time.sleep(0.02)
                continue
            try:
                p = self.dev.read_packet()
                self.q.put(tuple(p[c] for c in CHANNELS))
            except AFESerialError:
                try:                        # hiccup / stream ended -> restart
                    self.dev.reset_link()
                    self.dev.begin_streaming(N_STREAM)
                except Exception as e:
                    self.failed.emit("stream restart failed: %s" % e)
                    return

        try:
            if self._streaming:
                self.dev.stop_streaming()
            self.dev.close()
        except Exception:
            pass

    def _handle(self, cmd):
        try:
            if cmd[0] == "start":
                self.dev.reset_link()
                if self.dev.begin_streaming(N_STREAM):
                    self._streaming = True
                    self.status.emit("streaming")
                else:
                    self.failed.emit("could not start streaming")
            elif cmd[0] == "stop":
                if self._streaming:
                    self.dev.stop_streaming()
                self._streaming = False
                self.status.emit("stopped")
            elif cmd[0] == "set_led":
                was = self._streaming
                if was:
                    self.dev.stop_streaming()
                self.dev.set_led_current(cmd[1], cmd[2])
                if was:
                    self.dev.begin_streaming(N_STREAM)
        except AFESerialError as e:
            self.status.emit("command error: %s" % e)


# --------------------------------------------------------------------------- #
#  Main window                                                                #
# --------------------------------------------------------------------------- #
class LiveViewer(QtWidgets.QMainWindow):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.setWindowTitle("AFE4490 SpO2 EVM  -  Live PPG (direct serial)")
        self.resize(1440, 820)
        self.setMinimumSize(1200, 740)
        self.setStyleSheet(STYLE)

        # state
        self.acquiring = False
        self.finite = False
        self.finite_seconds = 30
        self.t0 = 0.0
        self._last_t = 0.0
        self._sample_index = 0
        self._lp = {k: None for k in DISP_KEYS}   # per-channel low-pass state
        self._dc = {k: None for k in DISP_KEYS}   # per-channel DC-tracker state
        self._rate_n = 0
        self._rate_t0 = time.perf_counter()
        self.current_R = float("nan")
        self._hr_hist = deque(maxlen=HR_SMOOTH)
        self.axis_font = QtGui.QFont("Segoe UI", 9)

        # display buffers, one deque per channel (ir, red, ir_amb, red_amb)
        self.disp_t = deque()
        self.disp = {k: deque() for k in DISP_KEYS}
        an_max = int(ANALYSIS_MAX_SECONDS * FS_NOMINAL * 1.1)
        self.an_t = deque(maxlen=an_max)
        self.an_ir = deque(maxlen=an_max)
        self.an_red = deque(maxlen=an_max)
        self.hr_trend_t = deque()
        self.hr_trend = deque()
        self._spec_ema = None
        self.mod_t = deque()
        self.mod = {"ir": deque(), "red": deque()}
        self._mod_lp = {"ir": None, "red": None}
        self._mod_dc = {"ir": None, "red": None}
        self.rec = deque(maxlen=int(RECORD_MAX_SECONDS * FS_NOMINAL))  # (t, 6 chans)

        self.q = queue.Queue()
        self._build_ui()

        # worker
        self.worker = StreamWorker(port, self.q)
        self.worker.connected.connect(self._on_connected)
        self.worker.status.connect(self._on_status)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

        # timers
        self.draw_timer = QtCore.QTimer(self); self.draw_timer.timeout.connect(self._drain_and_draw)
        self.draw_timer.start(30)
        self.an_timer = QtCore.QTimer(self); self.an_timer.timeout.connect(self._update_analysis)
        self.an_timer.start(250)

    # ---- UI construction ------------------------------------------------ #
    def _build_ui(self):
        tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._acquisition_tab(), "Acquisition")
        tabs.addTab(self._analysis_tab(), "Analysis")

        sb = self.statusBar()
        self.lbl_conn = QtWidgets.QLabel("connecting...")
        self.lbl_rate = QtWidgets.QLabel("-- Hz"); self.lbl_rate.setProperty("class", "mono")
        self.lbl_elapsed = QtWidgets.QLabel("0.0 s"); self.lbl_elapsed.setProperty("class", "mono")
        sb.addWidget(self.lbl_conn, 1)
        sb.addPermanentWidget(QtWidgets.QLabel("rate:")); sb.addPermanentWidget(self.lbl_rate)
        sb.addPermanentWidget(QtWidgets.QLabel("elapsed:")); sb.addPermanentWidget(self.lbl_elapsed)

    # ---- plot styling helpers ------------------------------------------ #
    def _style_axes(self, p, legend=False):
        p.setBackground("w")
        p.showGrid(x=True, y=True, alpha=0.12)
        for name in ("bottom", "left"):
            ax = p.getAxis(name)
            ax.setPen(pg.mkPen(COL_AXIS))
            ax.setTextPen(pg.mkPen(COL_TEXT))
            ax.setStyle(tickFont=self.axis_font)
        if legend:
            p.addLegend(offset=(10, 8), labelTextColor=COL_TEXT,
                        brush=pg.mkBrush(255, 255, 255, 220), pen=pg.mkPen("#e0e3e8"))
        return p

    def _plabel(self, p, side, text, units=None):
        p.setLabel(side, text, units=units, color=COL_TEXT, **{"font-size": "10pt"})

    def _acquisition_tab(self):
        w = QtWidgets.QWidget(); lay = QtWidgets.QHBoxLayout(w)

        # LED1 (IR) and LED2 (Red) on separate, vertically-stacked plots whose
        # time axes scroll together. Each can optionally overlay its ambient
        # (background) channel.
        plots = QtWidgets.QVBoxLayout()
        self.plot_ir = pg.PlotWidget()
        self._style_axes(self.plot_ir, legend=True)
        self._plabel(self.plot_ir, "left", "IR (LED1)")
        self.plot_ir.setMouseEnabled(x=False, y=True)
        self.curve_ir = self.plot_ir.plot(pen=IR_PEN, name="IR")
        self.curve_ir_amb = self.plot_ir.plot(pen=AMB_PEN, name="ambient")

        self.plot_red = pg.PlotWidget()
        self._style_axes(self.plot_red, legend=True)
        self._plabel(self.plot_red, "bottom", "time", "s")
        self._plabel(self.plot_red, "left", "Red (LED2)")
        self.plot_red.setMouseEnabled(x=False, y=True)
        self.curve_red = self.plot_red.plot(pen=RED_PEN, name="Red")
        self.curve_red_amb = self.plot_red.plot(pen=AMB_PEN, name="ambient")

        self.plot_red.setXLink(self.plot_ir)          # scroll the two together
        plots.addWidget(self.plot_ir); plots.addWidget(self.plot_red)
        lay.addLayout(plots, stretch=3)

        panel = QtWidgets.QVBoxLayout(); lay.addLayout(panel, stretch=0)
        panel.setSpacing(8)

        # --- capture group ---
        gb = QtWidgets.QGroupBox("Capture"); gl = QtWidgets.QVBoxLayout(gb)
        self.rb_cont = QtWidgets.QRadioButton("Continuous"); self.rb_cont.setChecked(True)
        self.rb_fin = QtWidgets.QRadioButton("Finite")
        finrow = QtWidgets.QHBoxLayout()
        self.spin_sec = QtWidgets.QSpinBox(); self.spin_sec.setRange(1, RECORD_MAX_SECONDS)
        self.spin_sec.setValue(30); self.spin_sec.setSuffix(" s"); self.spin_sec.setEnabled(False)
        self.rb_fin.toggled.connect(self.spin_sec.setEnabled)
        finrow.addWidget(self.rb_fin); finrow.addWidget(self.spin_sec); finrow.addStretch(1)
        gl.addWidget(self.rb_cont); gl.addLayout(finrow)

        self.btn_start = QtWidgets.QPushButton("Start"); self.btn_start.setObjectName("start")
        self.btn_start.setCheckable(True); self.btn_start.toggled.connect(self._on_start_toggled)
        gl.addWidget(self.btn_start)
        self.btn_save = QtWidgets.QPushButton("Save waveform..."); self.btn_save.clicked.connect(self._save)
        gl.addWidget(self.btn_save)
        panel.addWidget(gb)

        # --- display group ---
        gb2 = QtWidgets.QGroupBox("Display"); gl2 = QtWidgets.QVBoxLayout(gb2)
        self.chk_dc = QtWidgets.QCheckBox("Remove DC  (show pulsatile AC)")
        self.chk_dc.stateChanged.connect(self._on_dc_toggle)
        gl2.addWidget(self.chk_dc)
        self.chk_ambient = QtWidgets.QCheckBox("Show ambient / background")
        self.chk_ambient.stateChanged.connect(self._on_ambient_toggle)
        gl2.addWidget(self.chk_ambient)
        self.chk_lowpass = QtWidgets.QCheckBox("Reduce high-frequency noise (display low-pass)")
        self.chk_lowpass.setChecked(True)
        self.chk_lowpass.stateChanged.connect(self._on_display_filter_changed)
        gl2.addWidget(self.chk_lowpass)
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("Low-pass cutoff:"))
        self.spin_lowpass = QtWidgets.QDoubleSpinBox()
        self.spin_lowpass.setRange(2.0, 40.0); self.spin_lowpass.setDecimals(1)
        self.spin_lowpass.setSingleStep(1.0); self.spin_lowpass.setValue(8.0)
        self.spin_lowpass.setSuffix(" Hz")
        self.spin_lowpass.valueChanged.connect(self._on_display_filter_changed)
        filter_row.addWidget(self.spin_lowpass); filter_row.addStretch(1)
        gl2.addLayout(filter_row)
        raw_note = QtWidgets.QLabel("Display only - saved CSV and SpO2 analysis keep the original samples.")
        raw_note.setWordWrap(True); raw_note.setStyleSheet("color:palette(mid);")
        gl2.addWidget(raw_note)
        self.lbl_vals = QtWidgets.QLabel("IR: --    Red: --"); self.lbl_vals.setProperty("class", "mono")
        gl2.addWidget(self.lbl_vals)
        panel.addWidget(gb2)

        # --- LED group ---
        gb3 = QtWidgets.QGroupBox("LED drive current  (code 0-255)"); gl3 = QtWidgets.QVBoxLayout(gb3)
        self.sld_ir, irb = self._slider("IR  (LED1)")
        self.sld_red, redb = self._slider("Red (LED2)")
        self.sld_ir.sliderReleased.connect(self._on_led_change)
        self.sld_red.sliderReleased.connect(self._on_led_change)
        gl3.addLayout(irb); gl3.addLayout(redb)
        panel.addWidget(gb3)
        panel.addStretch(1)
        return w

    def _analysis_tab(self):
        outer = QtWidgets.QWidget(); outer_lay = QtWidgets.QVBoxLayout(outer)
        intro = QtWidgets.QLabel(
            "Follow one live analysis window from the two optical waveforms to R, "
            "then compare an ideal Beer-Lambert prediction with a calibration curve.")
        intro.setWordWrap(True)
        outer_lay.addWidget(intro)

        inner = QtWidgets.QTabWidget()
        inner.addTab(self._spo2_walkthrough(), "SpO2 walkthrough")
        inner.addTab(self._heart_rate_panel(), "Heart rate")
        outer_lay.addWidget(inner, 1)
        return outer

    def _heart_rate_panel(self):
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)

        # top row: selected HR method + big readout + analysis controls
        top = QtWidgets.QHBoxLayout()
        self.fft_plot = pg.PlotWidget()
        self._style_axes(self.fft_plot)
        self._plabel(self.fft_plot, "bottom", "heart rate", "bpm")
        self._plabel(self.fft_plot, "left", "spectral power")
        self.fft_plot.setXRange(30, 220)
        fill = pg.mkColor(COL_IR); fill.setAlpha(45)
        self.fft_curve = self.fft_plot.plot(pen=IR_PEN, fillLevel=0, brush=fill)
        self.peak_curve = self.fft_plot.plot(pen=IR_PEN)
        self.peak_curve.hide()
        self.peak_markers = pg.ScatterPlotItem(
            size=9, brush=pg.mkBrush(COL_RED), pen=pg.mkPen("white", width=1.0))
        self.peak_markers.hide()
        self.fft_plot.addItem(self.peak_markers)
        self.hr_marker = pg.InfiniteLine(angle=90, movable=False,
                                         pen=pg.mkPen(COL_RED, width=1.5, style=QtCore.Qt.DashLine))
        self.fft_plot.addItem(self.hr_marker)
        top.addWidget(self.fft_plot, 3)

        side = QtWidgets.QVBoxLayout(); side.addStretch(1)
        cap = QtWidgets.QLabel("Estimated HR"); cap.setStyleSheet("color:#5a616b;")
        side.addWidget(cap)
        self.lbl_hr = QtWidgets.QLabel("--"); self.lbl_hr.setObjectName("hr")
        side.addWidget(self.lbl_hr)
        side.addWidget(QtWidgets.QLabel("bpm"))
        side.addSpacing(12)
        side.addWidget(QtWidgets.QLabel("Method:"))
        self.cmb_hr_method = QtWidgets.QComboBox()
        self.cmb_hr_method.addItems(["FFT spectrum", "Peak selection"])
        self.cmb_hr_method.setMinimumWidth(180)
        self.cmb_hr_method.currentIndexChanged.connect(self._on_hr_method_changed)
        side.addWidget(self.cmb_hr_method)
        self.lbl_hr_method = QtWidgets.QLabel("Dominant frequency in the pulse band")
        self.lbl_hr_method.setWordWrap(True)
        self.lbl_hr_method.setStyleSheet("color:#6a717b;")
        side.addWidget(self.lbl_hr_method)
        side.addSpacing(12)
        hwin = QtWidgets.QHBoxLayout()
        hwin.addWidget(QtWidgets.QLabel("HR window:"))
        self.spin_hr_win = QtWidgets.QSpinBox()
        self.spin_hr_win.setRange(2, ANALYSIS_MAX_SECONDS)
        self.spin_hr_win.setValue(HR_WIN_DEFAULT); self.spin_hr_win.setSuffix(" s")
        hwin.addWidget(self.spin_hr_win); hwin.addStretch(1)
        side.addLayout(hwin); side.addStretch(1)
        top.addLayout(side, 1)
        v.addLayout(top, 1)

        # bottom: estimated HR over time (scrolling)
        self.hr_trend_plot = pg.PlotWidget()
        self._style_axes(self.hr_trend_plot)
        self._plabel(self.hr_trend_plot, "bottom", "time", "s")
        self._plabel(self.hr_trend_plot, "left", "heart rate", "bpm")
        self.hr_trend_plot.setYRange(40, 140)
        self.hr_trend_plot.setMouseEnabled(x=False, y=True)
        self.hr_curve = self.hr_trend_plot.plot(
            pen=pg.mkPen(COL_RED, width=2), symbol="o", symbolSize=4,
            symbolBrush=COL_RED, symbolPen=None)
        v.addWidget(self.hr_trend_plot, 1)
        return w

    def _spo2_walkthrough(self):
        w = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(w)

        # Step 1: the same pulse expressed as fractional modulation.  Plotting
        # AC/DC directly makes unequal LED brightness/DC levels disappear.
        step1 = QtWidgets.QGroupBox("1. Normalize each pulsatile waveform by its own DC level")
        s1 = QtWidgets.QHBoxLayout(step1)
        self.mod_plot = pg.PlotWidget()
        self._style_axes(self.mod_plot, legend=True)
        self._plabel(self.mod_plot, "bottom", "time", "s")
        self._plabel(self.mod_plot, "left", "AC / DC", "%")
        self.mod_ir_curve = self.mod_plot.plot(pen=IR_PEN, name="IR: AC_IR / DC_IR")
        self.mod_red_curve = self.mod_plot.plot(pen=RED_PEN, name="Red: AC_red / DC_red")
        s1.addWidget(self.mod_plot, 3)

        readout = QtWidgets.QVBoxLayout()
        spwin = QtWidgets.QHBoxLayout()
        spwin.addWidget(QtWidgets.QLabel("SpO2 window:"))
        self.spin_spo2_win = QtWidgets.QSpinBox()
        self.spin_spo2_win.setRange(2, ANALYSIS_MAX_SECONDS)
        self.spin_spo2_win.setValue(SPO2_WIN_DEFAULT); self.spin_spo2_win.setSuffix(" s")
        spwin.addWidget(self.spin_spo2_win); spwin.addStretch(1)
        readout.addLayout(spwin)
        self.lbl_quality = QtWidgets.QLabel("Waiting for a stable pulse...")
        self.lbl_quality.setObjectName("qualityWait")
        self.lbl_quality.setWordWrap(True)
        readout.addWidget(self.lbl_quality)
        form = QtWidgets.QFormLayout()
        self.lbl_acdc_ir = QtWidgets.QLabel("--"); self.lbl_acdc_ir.setProperty("class", "mono")
        self.lbl_acdc_red = QtWidgets.QLabel("--"); self.lbl_acdc_red.setProperty("class", "mono")
        self.lbl_corr = QtWidgets.QLabel("--"); self.lbl_corr.setProperty("class", "mono")
        form.addRow("IR modulation (RMS):", self.lbl_acdc_ir)
        form.addRow("Red modulation (RMS):", self.lbl_acdc_red)
        form.addRow("Pulse similarity:", self.lbl_corr)
        readout.addLayout(form)
        explanation = QtWidgets.QLabel(
            "The DC level is mostly static tissue and optical coupling. The small AC "
            "wave is the arterial volume change. Dividing AC by DC makes each colour "
            "a fractional pulse, so their amplitudes can be compared.")
        explanation.setWordWrap(True); explanation.setStyleSheet("color:palette(mid);")
        readout.addWidget(explanation); readout.addStretch(1)
        s1.addLayout(readout, 2)
        lay.addWidget(step1, 3)

        lower = QtWidgets.QHBoxLayout()

        # Step 2: show the two ratios as bars and the ratio-of-ratios equation.
        step2 = QtWidgets.QGroupBox("2. Divide the two fractional pulse amplitudes")
        s2 = QtWidgets.QVBoxLayout(step2)
        self.ratio_plot = pg.PlotWidget()
        self._style_axes(self.ratio_plot)
        self._plabel(self.ratio_plot, "left", "RMS AC / DC", "%")
        self.ratio_plot.getAxis("bottom").setTicks([[(0, "IR"), (1, "Red")]])
        self.ratio_plot.setXRange(-0.7, 1.7)
        self.ratio_bars = pg.BarGraphItem(x=[0, 1], height=[0, 0], width=0.55,
                                           brushes=[pg.mkBrush(COL_IR), pg.mkBrush(COL_RED)])
        self.ratio_plot.addItem(self.ratio_bars)
        s2.addWidget(self.ratio_plot, 1)
        self.lbl_ratio = QtWidgets.QLabel("R = (AC/DC)red / (AC/DC)IR = --")
        self.lbl_ratio.setObjectName("equation")
        self.lbl_ratio.setAlignment(QtCore.Qt.AlignCenter)
        s2.addWidget(self.lbl_ratio)
        lower.addWidget(step2, 2)

        # Step 3: mapping choice and a live calibration curve.
        step3 = QtWidgets.QGroupBox("3. Map R to an oxygen saturation")
        s3 = QtWidgets.QHBoxLayout(step3)
        self.cal_plot = pg.PlotWidget()
        self._style_axes(self.cal_plot)
        self._plabel(self.cal_plot, "bottom", "ratio of ratios, R")
        self._plabel(self.cal_plot, "left", "predicted SpO2", "%")
        self.cal_plot.setXRange(0.2, 1.6); self.cal_plot.setYRange(50, 105)
        self.cal_curve = self.cal_plot.plot(pen=pg.mkPen(COL_CURVE, width=2))
        self.cal_point = pg.ScatterPlotItem(size=13, brush=pg.mkBrush(COL_IR),
                                            pen=pg.mkPen("white", width=1.5))
        self.cal_plot.addItem(self.cal_point)
        s3.addWidget(self.cal_plot, 3)

        controls = QtWidgets.QVBoxLayout()
        self.lbl_spo2 = QtWidgets.QLabel("--"); self.lbl_spo2.setObjectName("spo2")
        self.lbl_spo2.setAlignment(QtCore.Qt.AlignCenter)
        controls.addWidget(self.lbl_spo2)
        unit = QtWidgets.QLabel("%  teaching estimate"); unit.setAlignment(QtCore.Qt.AlignCenter)
        controls.addWidget(unit)
        self.cmb_spo2_model = QtWidgets.QComboBox()
        self.cmb_spo2_model.addItems(["Custom R relationship", "Ideal Beer-Lambert"])
        self.cmb_spo2_model.currentIndexChanged.connect(self._on_model_changed)
        controls.addWidget(self.cmb_spo2_model)

        self.model_stack = QtWidgets.QStackedWidget()
        self.model_stack.setMinimumWidth(330)
        self.model_stack.addWidget(self._custom_model_controls())
        self.model_stack.addWidget(self._beer_model_controls())
        controls.addWidget(self.model_stack)
        self.lbl_model_equation = QtWidgets.QLabel("SpO2 = a + bR + cR^2")
        self.lbl_model_equation.setObjectName("equation")
        self.lbl_model_equation.setWordWrap(True)
        controls.addWidget(self.lbl_model_equation)
        controls.addStretch(1)
        s3.addLayout(controls, 2)
        lower.addWidget(step3, 3)
        lay.addLayout(lower, 3)
        return w

    def _spin(self, value, minimum=-10000.0, maximum=10000.0, decimals=2, step=1.0):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum); spin.setDecimals(decimals)
        spin.setSingleStep(step); spin.setValue(value)
        spin.setMinimumWidth(135)
        spin.valueChanged.connect(self._refresh_calibration_plot)
        return spin

    def _custom_model_controls(self):
        w = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(w)
        form.setContentsMargins(0, 4, 0, 4)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.spin_a = self._spin(110.0)
        self.spin_b = self._spin(-25.0)
        self.spin_c = self._spin(0.0)
        form.addRow("a:", self.spin_a); form.addRow("b:", self.spin_b); form.addRow("c:", self.spin_c)
        return w

    def _beer_model_controls(self):
        w = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(w)
        form.setContentsMargins(0, 4, 0, 4)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.spin_o2_red = self._spin(EPS_HBO2_RED, 0, 10000, 2, 10)
        self.spin_hb_red = self._spin(EPS_HB_RED, 0, 10000, 2, 10)
        self.spin_o2_ir = self._spin(EPS_HBO2_IR, 0, 10000, 2, 10)
        self.spin_hb_ir = self._spin(EPS_HB_IR, 0, 10000, 2, 10)
        self.spin_path = self._spin(1.0, 0.1, 3.0, 3, 0.05)
        form.addRow("epsilon HbO2, red:", self.spin_o2_red)
        form.addRow("epsilon Hb, red:", self.spin_hb_red)
        form.addRow("epsilon HbO2, IR:", self.spin_o2_ir)
        form.addRow("epsilon Hb, IR:", self.spin_hb_ir)
        form.addRow("path red / IR:", self.spin_path)
        return w

    def _on_model_changed(self, index):
        self.model_stack.setCurrentIndex(index)
        if index == 0:
            self.lbl_model_equation.setText("SpO2 = a + bR + cR^2")
        else:
            self.lbl_model_equation.setText(
                "Beer-Lambert: solve delta A(lambda) = [epsilon_O2 S + "
                "epsilon_Hb (1-S)] delta L at red and IR")
        self._refresh_calibration_plot()

    def _spo2_for_R(self, R):
        R = np.asarray(R, dtype=float)
        if self.cmb_spo2_model.currentIndex() == 0:
            return self.spin_a.value() + self.spin_b.value() * R + self.spin_c.value() * R * R
        return spo2_beer_lambert(
            R, self.spin_o2_red.value(), self.spin_hb_red.value(),
            self.spin_o2_ir.value(), self.spin_hb_ir.value(), self.spin_path.value())

    def _refresh_calibration_plot(self):
        if not hasattr(self, "cal_curve"):
            return
        rs = np.linspace(0.2, 1.6, 250)
        ys = self._spo2_for_R(rs)
        good = np.isfinite(ys) & (ys > -50) & (ys < 150)
        self.cal_curve.setData(rs[good], ys[good])
        if np.isfinite(self.current_R):
            spo2 = float(self._spo2_for_R(self.current_R))
            if np.isfinite(spo2):
                self.cal_point.setData([self.current_R], [spo2])
                self.lbl_spo2.setText("%.1f" % np.clip(spo2, 0, 100))

    def _slider(self, label):
        box = QtWidgets.QHBoxLayout()
        sld = QtWidgets.QSlider(QtCore.Qt.Horizontal); sld.setRange(0, 255); sld.setValue(0x14)
        lab = QtWidgets.QLabel(label); lab.setFixedWidth(70); lab.setProperty("class", "mono")
        box.addWidget(lab); box.addWidget(sld)
        return sld, box

    # ---- acquisition control ------------------------------------------- #
    def _on_start_toggled(self, on):
        if on:
            self.finite = self.rb_fin.isChecked()
            self.finite_seconds = self.spin_sec.value()
            self._reset_capture()
            self.acquiring = True
            self.worker.post(("start",))
            self.btn_start.setText("Stop")
            self._set_mode_enabled(False)
        else:
            self.acquiring = False
            self.worker.post(("stop",))
            self.btn_start.setText("Start")
            self._set_mode_enabled(True)

    def _set_mode_enabled(self, en):
        self.rb_cont.setEnabled(en); self.rb_fin.setEnabled(en)
        self.spin_sec.setEnabled(en and self.rb_fin.isChecked())

    def _clear_display(self):
        self.disp_t.clear()
        for k in DISP_KEYS:
            self.disp[k].clear()
            self._lp[k] = None
            self._dc[k] = None

    def _reset_capture(self):
        self.t0 = time.perf_counter()
        self._last_t = 0.0
        self._sample_index = 0
        self._clear_display()
        for d in (self.an_t, self.an_ir, self.an_red, self.rec,
                  self.hr_trend_t, self.hr_trend,
                  self.mod_t, self.mod["ir"], self.mod["red"]):
            d.clear()
        self._hr_hist.clear()
        self._spec_ema = None
        self._mod_lp = {"ir": None, "red": None}
        self._mod_dc = {"ir": None, "red": None}

    # ---- live update ---------------------------------------------------- #
    def _drain_and_draw(self):
        batch = []
        while True:
            try:
                batch.append(self.q.get_nowait())
            except queue.Empty:
                break

        if not self.acquiring:
            return

        now = time.perf_counter() - self.t0
        if batch:
            n = len(batch)
            # The stream contains no timestamps or sequence numbers. With the
            # deterministic 500-Hz EVM profile, sample index is the least-jittery
            # time base and avoids duplicate times at GUI batch boundaries.
            times = (self._sample_index + np.arange(n, dtype=float)) / FS_NOMINAL
            self._sample_index += n
            self._last_t = times[-1]
            # channel key -> raw packet index
            src = {"ir": IDX_IR, "red": IDX_RED, "ir_amb": IDX_ALED1, "red_amb": IDX_ALED2}
            lp_on = self.chk_lowpass.isChecked()
            dc_on = self.chk_dc.isChecked()
            # optional one-pole display low-pass (the full ~500 Hz stream looks
            # noisy); this changes the PLOT only -- analysis + recording keep raw.
            alpha = (1.0 - np.exp(-2.0 * np.pi * self.spin_lowpass.value() / FS_NOMINAL)
                     if lp_on else 0.0)
            for tup, tt in zip(batch, times):
                for k, idx in src.items():
                    val = tup[idx]
                    if lp_on:
                        self._lp[k] = val if self._lp[k] is None else self._lp[k] + alpha * (val - self._lp[k])
                        v = self._lp[k]
                    else:
                        v = val
                    self._dc[k] = v if self._dc[k] is None else (1 - EMA_ALPHA) * self._dc[k] + EMA_ALPHA * v
                    self.disp[k].append(v - self._dc[k] if dc_on else v)
                self.disp_t.append(tt)
                self.an_t.append(tt); self.an_ir.append(tup[IDX_IR]); self.an_red.append(tup[IDX_RED])
                self.rec.append((tt,) + tup)
                # SpO2 modulation waveforms: per-sample 2-pole band-pass -> AC/DC %
                # (independent of the acquisition-tab display toggles).
                for mk, midx in (("ir", IDX_IR), ("red", IDX_RED)):
                    raw = tup[midx]
                    lp = self._mod_lp[mk]
                    lp = raw if lp is None else lp + A_MOD_LP * (raw - lp)
                    self._mod_lp[mk] = lp
                    dc = self._mod_dc[mk]
                    dc = lp if dc is None else dc + A_MOD_HP * (lp - dc)
                    self._mod_dc[mk] = dc
                    self.mod[mk].append(100.0 * (lp - dc) / dc if dc else 0.0)
                self.mod_t.append(tt)

            tmin = now - WINDOW_SECONDS
            while self.disp_t and self.disp_t[0] < tmin:
                self.disp_t.popleft()
                for k in DISP_KEYS:
                    self.disp[k].popleft()

            tarr = np.fromiter(self.disp_t, float)
            self.curve_ir.setData(tarr, np.fromiter(self.disp["ir"], float))
            self.curve_red.setData(tarr, np.fromiter(self.disp["red"], float))
            if self.chk_ambient.isChecked():
                self.curve_ir_amb.setData(tarr, np.fromiter(self.disp["ir_amb"], float))
                self.curve_red_amb.setData(tarr, np.fromiter(self.disp["red_amb"], float))
            self.plot_ir.setXRange(max(0.0, now - WINDOW_SECONDS), now, padding=0)
            self.lbl_vals.setText("IR: %8d    Red: %8d" % (batch[-1][IDX_IR], batch[-1][IDX_RED]))

            # SpO2 modulation waveforms scroll smoothly at the display rate
            mtmin = now - MOD_WINDOW_SECONDS
            while self.mod_t and self.mod_t[0] < mtmin:
                self.mod_t.popleft(); self.mod["ir"].popleft(); self.mod["red"].popleft()
            mt = np.fromiter(self.mod_t, float)
            self.mod_ir_curve.setData(mt, np.fromiter(self.mod["ir"], float))
            self.mod_red_curve.setData(mt, np.fromiter(self.mod["red"], float))
            self.mod_plot.setXRange(max(0.0, now - MOD_WINDOW_SECONDS), now, padding=0)

            self._rate_n += n
            dt = time.perf_counter() - self._rate_t0
            if dt >= 0.5:
                self.lbl_rate.setText("%.0f Hz" % (self._rate_n / dt))
                self._rate_n = 0; self._rate_t0 = time.perf_counter()

        self.lbl_elapsed.setText("%.1f s" % now)
        if self.finite and now >= self.finite_seconds:
            self.btn_start.setChecked(False)      # auto-stop -> triggers _on_start_toggled(False)

    # ---- analysis ------------------------------------------------------- #
    def _update_analysis(self):
        if len(self.an_t) < 64:
            return
        t_all = np.fromiter(self.an_t, float)
        ir_all = np.fromiter(self.an_ir, float)
        red_all = np.fromiter(self.an_red, float)
        span = t_all[-1] - t_all[0]
        if span <= 0:
            return
        fs = len(t_all) / span

        def tail(secs):
            n = int(max(64, min(len(t_all), round(secs * fs))))
            return t_all[-n:], ir_all[-n:], red_all[-n:]

        _, ir_hr, _ = tail(self.spin_hr_win.value())
        self._compute_hr(ir_hr, fs, self.spin_hr_win.value())

        t_sp, ir_sp, red_sp = tail(self.spin_spo2_win.value())
        self._compute_spo2(t_sp, ir_sp, red_sp, fs)

    def _compute_hr(self, ir, fs, window_seconds):
        if self.cmb_hr_method.currentIndex() == 0:
            self._compute_hr_fft(ir, fs)
        else:
            self._compute_hr_peaks(ir, fs, window_seconds)

    def _compute_hr_fft(self, ir, fs):
        n = len(ir)
        if n < 64 or not np.isfinite(fs) or fs <= 0:
            return
        # detrend (remove DC + slope) + Hann window, then a zero-padded FFT for a
        # smooth, finely-binned spectrum
        x = np.asarray(ir, float)
        x = (x - np.linspace(x[0], x[-1], n)) * np.hanning(n)
        N = max(HR_PAD_LEN, 1 << int(np.ceil(np.log2(n))))
        sp = np.abs(np.fft.rfft(x, n=N))
        freqs = np.fft.rfftfreq(N, 1.0 / fs)
        # average the spectrum across frames so the plot stops flickering
        if self._spec_ema is None or len(self._spec_ema) != len(sp):
            self._spec_ema = sp
        else:
            self._spec_ema = SPEC_EMA * sp + (1.0 - SPEC_EMA) * self._spec_ema
        sp = self._spec_ema

        bpm_axis = freqs * 60.0
        vis = (bpm_axis >= 30) & (bpm_axis <= 220)
        if vis.any():
            self.fft_curve.setData(bpm_axis[vis], sp[vis])
        band = (freqs >= HR_MIN_HZ) & (freqs <= HR_MAX_HZ)
        idx = np.flatnonzero(band)
        if len(idx) == 0:
            return
        k = int(idx[np.argmax(sp[idx])])
        conf = float(sp[k] / (np.median(sp[band]) + 1e-12))     # peak prominence
        delta = 0.0
        if 0 < k < len(sp) - 1:
            a, b, c = (np.log(sp[k - 1] + 1e-12), np.log(sp[k] + 1e-12),
                       np.log(sp[k + 1] + 1e-12))
            den = a - 2 * b + c
            if den < 0:
                delta = float(np.clip(0.5 * (a - c) / den, -0.5, 0.5))
        bpm_val = (k + delta) * (fs / N) * 60.0
        if conf >= HR_CONF_MIN and 30 <= bpm_val <= 220:
            self._publish_hr(bpm_val)
        elif not self._hr_hist:
            self.lbl_hr.setText("--")
        
    def _compute_hr_peaks(self, ir, fs, window_seconds):
        bpm_val, filtered, peaks = peak_count_rate(ir, fs, window_seconds)
        t = np.arange(len(filtered), dtype=float) / fs - window_seconds
        # Keep the plot responsive: the detector uses every sample, while the
        # screen needs at most roughly 1,500 points to draw the same shape.
        stride = max(1, int(np.ceil(len(filtered) / 1500.0)))
        self.peak_curve.setData(t[::stride], filtered[::stride])
        if len(peaks):
            self.peak_markers.setData(t[peaks], filtered[peaks])
        else:
            self.peak_markers.setData([], [])
        self.fft_plot.setXRange(-window_seconds, 0, padding=0)
        if np.isfinite(bpm_val) and 30 <= bpm_val <= 220:
            self._publish_hr(bpm_val)
        elif not self._hr_hist:
            self.lbl_hr.setText("--")

    def _publish_hr(self, bpm_val):
        self._hr_hist.append(float(bpm_val))
        if not self._hr_hist:
            self.lbl_hr.setText("--")
            return
        hr = float(np.median(self._hr_hist))
        self.lbl_hr.setText("%.0f" % hr)
        if self.cmb_hr_method.currentIndex() == 0:
            self.hr_marker.setValue(hr)
        if self.acquiring:
            now = time.perf_counter() - self.t0
            self.hr_trend_t.append(now); self.hr_trend.append(hr)
            while self.hr_trend_t and self.hr_trend_t[0] < now - HR_TREND_SECONDS:
                self.hr_trend_t.popleft(); self.hr_trend.popleft()
            self.hr_curve.setData(np.fromiter(self.hr_trend_t, float),
                                  np.fromiter(self.hr_trend, float))
            self.hr_trend_plot.setXRange(max(0.0, now - HR_TREND_SECONDS), now, padding=0)

    def _on_hr_method_changed(self, index):
        self._hr_hist.clear()
        self._spec_ema = None
        self.hr_trend_t.clear()
        self.hr_trend.clear()
        self.hr_curve.setData([], [])
        self.lbl_hr.setText("--")
        use_fft = index == 0
        self.fft_curve.setVisible(use_fft)
        self.hr_marker.setVisible(use_fft)
        self.peak_curve.setVisible(not use_fft)
        self.peak_markers.setVisible(not use_fft)
        if use_fft:
            self._plabel(self.fft_plot, "bottom", "heart rate", "bpm")
            self._plabel(self.fft_plot, "left", "spectral power")
            self.fft_plot.setXRange(30, 220)
            self.lbl_hr_method.setText("Dominant frequency in the pulse band")
        else:
            self._plabel(self.fft_plot, "bottom", "time relative to now", "s")
            self._plabel(self.fft_plot, "left", "filtered IR pulse")
            self.lbl_hr_method.setText(
                "Light smoothing; detected peaks / selected window x 60")

    def _compute_spo2(self, t, ir, red, fs):
        ac_ir_wave = bandpass_fft(ir, fs)
        ac_red_wave = bandpass_fft(red, fs)
        dc_ir = abs(float(np.mean(ir)))
        dc_red = abs(float(np.mean(red)))
        ac_ir = float(np.sqrt(np.mean(ac_ir_wave * ac_ir_wave)))
        ac_red = float(np.sqrt(np.mean(ac_red_wave * ac_red_wave)))
        r_ir = ac_ir / dc_ir if dc_ir > 1e-12 else float("nan")
        r_red = ac_red / dc_red if dc_red > 1e-12 else float("nan")
        R = r_red / r_ir if np.isfinite(r_ir) and r_ir > 1e-12 else float("nan")

        # (The Step-1 modulation waveforms are drawn in the fast display loop so
        # they scroll smoothly; here we only update the numeric R and the bars.)
        self.ratio_bars.setOpts(x=[0, 1], height=[100.0 * r_ir, 100.0 * r_red], width=0.55,
                                brushes=[pg.mkBrush(COL_IR), pg.mkBrush(COL_RED)])

        corr = float(np.corrcoef(ac_ir_wave, ac_red_wave)[0, 1]) if ac_ir and ac_red else float("nan")
        self.lbl_acdc_ir.setText("%.3f %%" % (100.0 * r_ir))
        self.lbl_acdc_red.setText("%.3f %%" % (100.0 * r_red))
        self.lbl_corr.setText("%.2f" % abs(corr))
        self.lbl_ratio.setText("R = %.4f / %.4f = %.3f" % (r_red, r_ir, R))

        span = t[-1] - t[0]
        stable = (span >= 4.0 and np.isfinite(R) and 0.05 < R < 2.5
                  and np.isfinite(corr) and abs(corr) >= 0.55
                  and r_ir > 0.00005 and r_red > 0.00005)
        if stable:
            self.lbl_quality.setText("Pulse detected - red and IR have matching rhythm")
            self.lbl_quality.setObjectName("qualityGood")
        else:
            self.lbl_quality.setText(
                "Low-confidence window - keep the finger still and wait for matching pulses")
            self.lbl_quality.setObjectName("qualityWait")
        self.lbl_quality.style().unpolish(self.lbl_quality)
        self.lbl_quality.style().polish(self.lbl_quality)

        self.current_R = R
        if np.isfinite(R):
            spo2 = float(self._spo2_for_R(R))
            if np.isfinite(spo2):
                self.lbl_spo2.setText("%.1f" % np.clip(spo2, 0, 100))
                self.cal_point.setData([R], [spo2])
            else:
                self.lbl_spo2.setText("--")
                self.cal_point.setData([], [])
        self._refresh_calibration_plot()

    # ---- misc slots ----------------------------------------------------- #
    def _autorange_plots(self):
        for p in (self.plot_ir, self.plot_red):
            p.enableAutoRange("y", True)

    def _on_dc_toggle(self):
        self._clear_display()
        self._autorange_plots()

    def _on_ambient_toggle(self):
        if not self.chk_ambient.isChecked():
            self.curve_ir_amb.setData([], [])
            self.curve_red_amb.setData([], [])
        self._autorange_plots()

    def _on_display_filter_changed(self):
        self._clear_display()
        self.spin_lowpass.setEnabled(self.chk_lowpass.isChecked())
        self._autorange_plots()

    def _on_led_change(self):
        self.worker.post(("set_led", self.sld_ir.value(), self.sld_red.value()))

    def _on_connected(self, s):
        self.lbl_conn.setText("connected:  " + s)

    def _on_status(self, s):
        self.lbl_conn.setText(s)

    def _on_failed(self, msg):
        self.lbl_conn.setText("NOT CONNECTED")
        self.btn_start.setChecked(False)
        QtWidgets.QMessageBox.critical(
            self, "Device error", msg +
            "\n\nCLOSE the TI GUI first (it holds the COM port), then relaunch,\n"
            "and check the selected serial port: %s" % self.port)

    def _save(self):
        if not self.rec:
            QtWidgets.QMessageBox.information(self, "Save waveform", "No data captured yet.")
            return
        # Never write into a macOS .app bundle (or a temporary one-file runtime).
        # Documents is writable and visible to students on both Windows and macOS.
        documents = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.DocumentsLocation)
        data_dir = os.path.join(documents or os.path.expanduser("~"),
                                "AFE4490 PulseOx data")
        os.makedirs(data_dir, exist_ok=True)
        default = os.path.join(data_dir, time.strftime("ppg_%Y%m%d_%H%M%S.csv"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save waveform", default, "CSV (*.csv)")
        if not path:
            return
        rows = list(self.rec)
        with open(path, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["time_s"] + CHANNELS)
            for row in rows:
                wr.writerow(["%.4f" % row[0]] + list(row[1:]))
        self.lbl_conn.setText("saved %d samples -> %s" % (len(rows), os.path.basename(path)))

    def closeEvent(self, ev):
        self.draw_timer.stop(); self.an_timer.stop()
        self.worker.stop(); self.worker.wait(2000)
        super().closeEvent(ev)


def _select_port(parent=None):
    """Return an explicit argument, an auto-detected TI port, or a user choice."""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        return sys.argv[1]
    available = list(list_ports.comports())
    ti_ports = [p.device for p in available
                if p.vid == TI_USB_VID and p.pid == TI_USB_PID]
    if ti_ports:
        return ti_ports[0]
    choices = [p.device for p in available]
    if sys.platform.startswith("win") and PORT_DEFAULT not in choices:
        choices.insert(0, PORT_DEFAULT)
    if choices:
        port, accepted = QtWidgets.QInputDialog.getItem(
            parent, "Select AFE4490 board", "Serial port:", choices, 0, False)
    else:
        hint = "COM4" if sys.platform.startswith("win") else "/dev/cu.usbmodem..."
        port, accepted = QtWidgets.QInputDialog.getText(
            parent, "Select AFE4490 board", "Serial port:",
            QtWidgets.QLineEdit.Normal, hint)
    return str(port) if accepted and port else None


def main():
    app = QtWidgets.QApplication(sys.argv)
    if "--self-test" in sys.argv:
        # Packaging check: exercise Qt/pyqtgraph and the peak-analysis dependency
        # without opening a serial port or requiring hardware.
        probe_plot = pg.PlotWidget()
        t = np.arange(4000, dtype=float) / 500.0
        bpm, _, peaks = peak_count_rate(np.sin(2 * np.pi * 1.25 * t), 500.0, 8.0)
        probe_plot.close()
        if len(peaks) != 10 or abs(bpm - 75.0) > 0.01:
            raise RuntimeError("packaged signal-processing self-test failed")
        return
    port = _select_port()
    if not port:
        return
    win = LiveViewer(port); win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
