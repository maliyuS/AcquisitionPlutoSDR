import time
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel


class SpectrumAnalyzer(pg.GraphicsLayoutWidget):
    def __init__(self, span=1, num_samples=2**18, sampling_rate=30e6, show=True, size=(500, 500), y1_axis=-50, y2_axis=50):
        super().__init__(show=show, size=size)

        # Variables du spectre à actualiser
        self.freqs = None
        self.power_rx0_dbm = None
        self.power_rx1_dbm = None

        # Paramètres d'acquisition
        self.numsamples = num_samples
        self.sampling_rate = sampling_rate

        # Paramètres d'affichage
        self.central_freq = 0 # Fréquence centrale en MHz
        self.span = span # Span en MHz
        self.y1_axis = y1_axis # limite basse axe des Y en dB
        self.y2_axis = y2_axis # limite haute axe des Y en dB
        self.markers = []

        # Configuration de la fenêtre FFT
        self.setup_plot_widget()

        # self.setup_fft_window()

        # Timer pour mettre à jour le graphique
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()


        ''' Set up FFT Window '''
    def setup_plot_widget(self):

        self.p1 = self.addPlot()
        self.p1.showGrid(x=True, y=True)

        ## Scale of span from the Editbox
        self.p1.setXRange(-self.span/2, self.span/2)
        self.p1.setYRange(self.y1_axis, self.y2_axis)
        self.p1.setLabel('bottom', "Frequency (MHz)", **{'color': '#FFF', 'size': '14pt'})
        self.p1.setLabel('left', "Amplitude (dB)", **{'color': '#FFF', 'size': '14pt'})

        # Curves
        self.baseCurve = self.p1.plot()

    def add_marker(self):
        """Add a movable marker to the plot."""
        if len(self.markers) < 2:
            marker = pg.InfiniteLine(pos=self.central_freq, angle=90, movable=True, pen=pg.mkPen('r', width=2))
            marker.sigPositionChanged.connect(self.update_marker_text)
            self.markers.append(marker)
            self.p1.addItem(marker)
            self.update_marker_text()

    def update_marker_text(self):
        """Update text labels for markers showing frequency and amplitude."""
        for i in reversed(range(self.marker_info_layout.count())):
            self.marker_info_layout.itemAt(i).widget().setParent(None)

        if len(self.markers) == 2:
            marker_info = []
            for i, marker in enumerate(self.markers):
                freq = marker.value()
                idx = np.abs(self.freqs - freq).argmin()
                amplitude_db = self.power_rx0[idx]
                marker_info.append(f"M{i + 1}: {freq:.2f} kHz, {amplitude_db:.2f} dB")
                self.marker_info_layout.addWidget(QLabel(marker_info[-1]))

            delta_freq = abs(self.markers[1].value() - self.markers[0].value())
            delta_amp = abs(
                float(marker_info[1].split(', ')[1].split()[0]) -
                float(marker_info[0].split(', ')[1].split()[0])
            )
            delta_label = QLabel(f"ΔF: {delta_freq:.2f} kHz, ΔA: {delta_amp:.2f} dB")
            self.marker_info_layout.addWidget(delta_label)

    def set_span(self, span):
        self.p1.setXRange(-span/2, span/2)

    # Calcul de la FFT
    def compute_fft(self, Rx0, Rx1):

        # Calculer le signal fenêtré
        windowed_Rx0 = Rx0 * np.blackman(len(Rx0))
        windowed_Rx1 = Rx1 * np.blackman(len(Rx1))

        # Calculer la FFT pour les deux cannaux
        fft_Rx0 = np.fft.fftshift(np.abs(np.fft.fft(windowed_Rx0, len(Rx0))))
        fft_Rx0 /= np.sum(np.blackman(len(Rx0)))

        fft_Rx1 = np.fft.fftshift(np.abs(np.fft.fft(windowed_Rx1, len(Rx1))))
        fft_Rx1 /= np.sum(np.blackman(len(Rx1)))

        # Conversion des amplitudes en puissances
        power_rx0 = np.abs(fft_Rx0) ** 2
        power_rx1 = np.abs(fft_Rx1) ** 2

        # Référence de puissances (1mW pour une conversion en dBm)
        P_ref = 1e-3

        # Conversion des puissances en dBm
        self.power_rx0_dbm = 10 * np.log10(abs(power_rx0 / P_ref) + 1e-9)
        self.power_rx1_dbm = 10 * np.log10(abs(power_rx1 / P_ref) + 1e-9)

        # Calculer l'axe des fréquences en kHz
        xf = np.fft.fftfreq(len(Rx0), 1/self.sampling_rate)
        self.freqs = np.fft.fftshift(xf) / 1e6


    # Mise à jour du graphique
    def update_plot(self):

        if self.power_rx0_dbm is not None and self.freqs is not None and self.power_rx1_dbm is not None:

            self.baseCurve.setData(self.freqs, self.power_rx0_dbm)