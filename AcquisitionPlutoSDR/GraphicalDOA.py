import pyqtgraph as pg
import numpy as np
import pyqtgraph
import pyqtgraph as pg
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

class GraphicalDOA (pg.GraphicsLayoutWidget):
    def __init__(self, color='w', show=True, size=(500, 500)):
        super().__init__(show=show, size=size)

        self.color=color

        self.tracking_length = 1000
        self.phase_cal = 0
        self.tracking_angles = np.ones(self.tracking_length) * 180
        self.tracking_angles[:-1] = -180   # make a line across the plot when tracking begins

        # Configuration de la fenêtre FFT
        self.setup_plot_widget()

        # Timer pour mettre à jour le graphique
        self.timer = QTimer()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

        ''' Set up FFT Window '''
    def setup_plot_widget(self):

        self.p1 = self.addPlot()
        self.p1.showGrid(x=True, alpha=1)
        self.p1.showAxis('left', show=False)

        self.p1.setXRange(-180, 180)
        self.p1.setYRange(0, self.tracking_length)
        self.p1.setLabel('bottom', 'Steering Angle', 'deg', **{'color': '#FFF', 'size': '14pt'})
        self.p1.setTitle('No Data', **{'color': '#FFF', 'size': '14pt'})
        self.fn = QtGui.QFont()
        self.fn.setPointSize(10)
        self.p1.getAxis("bottom").setTickFont(self.fn)

        # Curves
        self.baseCurve = self.p1.plot(pen=pyqtgraph.mkPen(self.color, width=2))  # Red curve

    def update_plot(self):

        self.baseCurve.setData(self.tracking_angles, np.arange(self.tracking_length))

    def updateDATA(self, tracking_angle):
        self.tracking_angles = np.append(self.tracking_angles, tracking_angle)
        self.tracking_angles = self.tracking_angles[1:]