import os

import PyQt5.QtWidgets
from PyQt5.QtCore import QTimer
from PyQt5 import QtWidgets
from GUI.GUI import Ui_MainWindow
from GUI.Chronometer import ChronometerThread
from dsp import MonopulseAngleEstimator
from GraphicalDOA import GraphicalDOA
from PlutoSetup import CustomSDR
from acquisition import AcquisitionThread
from unzip import convert_parquet_to_csv_and_delete
from SpectrumAnalyzer import SpectrumAnalyzer
from AD9363 import AD9363
import adi
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QGridLayout
)
import numpy as np

import sys


class MyGUI(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MyGUI, self).__init__()
        self.setupUi(self)

        # Calibration des puissances Rx0, Rx1, Tx0 et Tx1
        self.Rx1_cal = float(63.3)
        self.Rx0_cal = float(63.3)

        # Lier les boutons aux routines d'acquisition
        self.ConnectButton.clicked.connect(self.on_connectButton_click)
        self.AcquireButton.clicked.connect(self.on_acquisitionButton_click)
        self.STOPbutton.clicked.connect(self.on_stopButton_click)
        self.SigRef.currentIndexChanged.connect(self.on_SigRef)
        self.ComputeDOAButton.clicked.connect(self.on_computeDOAButton_click)

        #Lier les boutons aux routines pour enregistrer les données
        self.ScheduleButton.clicked.connect(self.on_scheduleButton_click)
        self.UnzipButton.clicked.connect(self.on_unzipButton_click)
        self.ImmediateRecordingButton.clicked.connect(self.on_immediateRecordingButton_click)

        # Lier les boutons du Tab spectrum Analyzer
        self.SPAN_input.returnPressed.connect(self.on_spanButton_click)
        self.AddMarkerButton.clicked.connect(self.on_addMarkerButton_click)

        # Initialiser les chronomètres Up/Down
        self.upChronometerThread = ChronometerThread(count_up=True)
        self.downChronometerThread = ChronometerThread(count_up=False)
        self.upChronometer = self.upChronometerThread.chronometer
        self.downChronometer = self.downChronometerThread.chronometer

        # Ajout d'un SpectrumAnalyzer pour chaque cannal
        self.Rx0analyzer = SpectrumAnalyzer("Rx0", "#FFC9B3")
        self.SpectrumLayoutRx0.addWidget(self.Rx0analyzer, 0, 0)

        self.Rx1analyzer = SpectrumAnalyzer("Rx1", "#B3F6FF")
        self.SpectrumLayoutRx1.addWidget(self.Rx1analyzer, 0, 0)

        # Ajout de l'UI pour visualiser les déphasages
        self.GraphicalDOA = GraphicalDOA()
        self.DOALayout.addWidget(self.GraphicalDOA, 0, 0)

        # Ajouter les fonctions événementielles pour les INPUT widgets de AoA estimation TAB
        self.phase_calibrationButton.clicked.connect(self.on_phase_calibrationButton_click)
        self.step_phase_input.returnPressed.connect(self.onPhaseStep_click)
        self.Fcarrier_input.returnPressed.connect(self.onFcarrier_click)
        self.Averaging_input.currentIndexChanged.connect(self.onAveraging)
        self.WindowSize.valueChanged.connect(self.on_WindowSize_changed)

        # Initialiser le dictionnaire pour stocker les données reçues
        self.data = {}
        self.AveragingEnabled = False

        # Instancier un Qtimer
        self.timer = QTimer()
        self.timer.timeout.connect(self.monitoring)
        self.timer.setInterval(100)
        self.timer.start(1000)

        # Lier les LineEdit aux routines de monitoring
        self.TxLO_input.returnPressed.connect(self.on_TxLO_input)
        self.RxLO_input.returnPressed.connect(self.on_RxLO_input)
        self.RxBW_input.returnPressed.connect(self.on_RxBW_input)
        self.TxBW_input.returnPressed.connect(self.on_TxBW_input)
        self.ADCRate_input.returnPressed.connect(self.on_ADCRate_input)
        self.ADCBuffer_input.returnPressed.connect(self.on_ADCBuffer_input)
        self.CentralFreq_input.returnPressed.connect(self.on_CentralFreq_input)

        # Initialiser les sliders de gains
        self.Rx0Gain_input.sliderReleased.connect(self.on_Rx0Gain_input)
        self.Rx1Gain_input.sliderReleased.connect(self.on_Rx1Gain_input)
        self.Tx0Gain_input.sliderReleased.connect(self.on_Tx0Gain_input)
        self.Tx1Gain_input.sliderReleased.connect(self.on_Tx1Gain_input)

        self.Rx1Gain_mode.currentIndexChanged.connect(self.on_Rx1Gain_mode)
        self.Rx0Gain_mode.currentIndexChanged.connect(self.on_Rx0Gain_mode)



########################################################################################################################
################################################# TAB MAIN MENU ########################################################
########################################################################################################################

    """Les fonctions évenementielles du Tab MainMenu"""

    def on_connectButton_click(self):
        '''Create Radios'''
        try:
            if hasattr(self, 'my_sdr'):
                self.log("Déjà connecté au PlutoSDR", color='red')
                return

            # Récupérer l'adresse IP du PlutoSDR
            uri = 'ip:' + self.ip_input.text()

            # Afficher que la connexion au Pluto à fonctionnée
            self.my_sdr = CustomSDR(uri=uri)
            self.my_sdr.configure_rx_properties()
            self.my_sdr.configure_tx_properties()
            self.my_sdr.configure_sampling_properties()

            # Instancier la classe de monitoring
            self.ad9363 = AD9363(uri=uri)
            self.ad9363_bis = adi.ad9361(uri=uri)

            # Prévenir avec le log que la connexion au PlutoSDR a réussie
            self.log("Connexion au PlutoSDR réussie", color='green')

            # Instancier les variables d'acquisition du Pluto dans le programme principal "main"
            # self.instanciate_acquisition_variables()

        except Exception as e:

            # Afficher dans le log l'erreur
            self.log("Erreur lors de la connexion au PlutoSDR", color='red')
            self.log(str(e), color='red')

########################################################################################################################
    # Initialiser le thread d'acquisition
    def on_acquisitionButton_click(self):

        # Si le sdr est vide, on ne peut pas lancer l'acquisition
        if not hasattr(self, 'my_sdr'):
            self.log("Veuillez d'abord vous connecter au PlutoSDR", color='red')
            return

        # Lancer le thread d'acquisition
        self.acquisition_thread = AcquisitionThread(self.my_sdr)
        self.log("Acquisition en cours ...", color='green')

        # Définir un slot pour stocker les données reçues
        def on_data_received(rx0, rx1):
            self.data['Rx0'] = rx0
            self.data['Rx1'] = rx1
            self.Rx0analyzer.compute_fft(rx0)
            self.Rx1analyzer.compute_fft(rx1)
            if hasattr(self, 'MonopulseAngleEstimator'):
                self.MonopulseAngleEstimator.set_new_data(rx0, rx1)

                # print("estimation angle: ", self.MonopulseAngleEstimator.last_phase_delay)
            # print("Data received:")
            # print("Rx_0:", self.data['Rx0'])
            # print("Rx_1:", self.data['Rx1'])

        # Connecter le signal data_received au slot on_data_received
        self.acquisition_thread.data_received.connect(on_data_received)

        # Démarrer le thread d'acquisition
        self.acquisition_thread.start()
########################################################################################################################
    def on_stopButton_click(self):

        # Arrêter le thread d'acquisition
        if hasattr(self, 'acquisition_thread'):
            self.acquisition_thread.stop()
            self.acquisition_thread.wait()
            del self.acquisition_thread
            self.log("Acquisition arrêtée", color='green')

        else:
            self.log("Aucune acquisition en cours", color='red')

########################################################################################################################
    def on_scheduleButton_click(self):

        # Vérification de l'existence de l'attribut après suppression
        if not hasattr(self, 'acquisition_thread'):
            self.log("Impossible de programmer un enregistrement: aucune acquisition en cours !", color='red')
            return

        # Récupérer le contenu de inputTimer_heure, inputTimer_minute et inputTimer_seconde
        hours = int(self.inputTimer_heure.text())
        minutes = int(self.inputTimer_minute.text())
        seconds = int(self.inputTimer_seconde.text())

        self.log('Enregistrement programmé dans : ' + f'{hours:02}:{minutes:02}:{seconds:02}', color='green')

        # Démarer le Chronometer et le connecter à la méthode on_timeUpdated
        self.startUpChronometer(hours, minutes, seconds)

########################################################################################################################
    def on_immediateRecordingButton_click(self):

        # Vérification de l'existence de l'attribut après suppression
        if not hasattr(self, 'acquisition_thread'):
            self.log("Veuillez d'abord lancer l'acquisition !", color='red')
            return

        self.acquisition_thread._ImmediateSaving = True

        self.log("Enregistrement d'une séquence d'acquisition ...", color='green')

########################################################################################################################
    def on_unzipButton_click(self):

        if hasattr(self, 'acquisition_thread'):
            self.log("Veuillez d'abord arrêter l'acquisition avant de décompresser les enregistrements", color='red')
            return

        # Décompresser les enregsitrements
        try:
            # Obtenir le répertoire courant
            current_directory = os.getcwd()

            # Ajouter le sous-répertoire '/recordings_temp'
            recordings_temp_directory = os.path.join(current_directory, 'recordings_temp')

            convert_parquet_to_csv_and_delete(recordings_temp_directory)
            self.log("Décompression des enregistrements terminée", color='green')

        except Exception as e:
            self.log("Erreur lors de la décompression des enregistrements", color='red')
            self.log(e, color='red')

    def on_SigRef(self):
        if hasattr(self, 'my_sdr'):
            if self.SigRef.currentText() == "ON":
                self.acquisition_thread._transmitting = True
            if self.SigRef.currentText() == "OFF":
                self.acquisition_thread._stopTransmitting = True

    def on_computeDOAButton_click(self):
        if hasattr(self, 'acquisition_thread'):
            self.log("Calibration déphasage en cours ...", color='green')

            self.MonopulseAngleEstimator = MonopulseAngleEstimator()
            self.MonopulseAngleEstimator.AoA_ready.connect(self.on_AoA_ready)
            self.MonopulseAngleEstimator.start()

########################################################################################################################

    """ Gérer les chronomètres Up/Down"""
    def startUpChronometer(self, hours, minutes, seconds):
        self.downChronometerThread.start()
        self.downChronometer.time_updated.connect(self.on_timeUpdated)
        self.downChronometer.start_timer(hours, minutes, seconds)
        self.changeColor("red")

########################################################################################################################
    def on_timeUpdated(self, hours, minutes, seconds):

        # Vérification de l'existence de l'attribut après suppression
        if not hasattr(self, 'acquisition_thread'):
            self.log("Attention: L'enregistrement à été déprogrammé !", color='orange')
            self.downChronometer.stop_timer()
            self.downChronometerThread.quit()
            self.outputTimer_heure.setText("00")
            self.outputTimer_minute.setText("00")
            self.outputTimer_seconde.setText("00")
            return

        # print(f'{hours:02}:{minutes:02}:{seconds:02}')
        self.outputTimer_heure.setText(f'{hours:02}')
        self.outputTimer_minute.setText(f'{minutes:02}')
        self.outputTimer_seconde.setText(f'{seconds:02}')


        # Si le chronomètre est terminé, arrêter le thread et démarrer l'enregistrement
        if hours == 0 and minutes == 0 and seconds == 0:
            # Arrêter le chronomètre
            self.downChronometer.stop_timer()
            self.downChronometerThread.quit()
            self.log("Chronomètre terminé", color='green')

            # Démarrer l'enregistrement
            self.log("Démarrage des enregistrements...", color='green')
            self.acquisition_thread._scheduleSaving = True

########################################################################################################################
    def changeColor(self, color):
        self.outputTimer_heure.setStyleSheet(f"color: {color}")
        self.outputTimer_minute.setStyleSheet(f"color: {color}")
        self.outputTimer_seconde.setStyleSheet(f"color: {color}")

########################################################################################################################
################################################# TAB SPECTRUM ANALYZER ################################################
########################################################################################################################

    """Les fonctions évenementielles du Tab Spectrum Analyzer"""
    def on_spanButton_click(self):
        # Vérification de l'éxistence de l'attribut après suppression
        if not hasattr(self, 'Rx0analyzer') or not hasattr(self, 'Rx1analyzer'):
            self.log("Impossible de changer le span: aucun Spectrum Analyzer disponible", color='red')
            return

        # Récupérer le contenu de l'input span
        span = float(self.SPAN_input.text())

        # Changer le span du Spectrum Analyzer
        self.Rx0analyzer.set_span(span)
        self.Rx1analyzer.set_span(span)

########################################################################################################################
    def on_addMarkerButton_click(self):
        # Vérification de l'éxistence de l'attribut après suppression
        if not hasattr(self, 'Rx0analyzer') or not hasattr(self, 'Rx1analyzer'):
            self.log("Impossible d'ajouter un marqueur: aucun Spectrum Analyzer disponible", color='red')
            return

        # Ajouter un marqueur au Spectrum Analyzer
        self.Rx0analyzer.add_marker()
        self.Rx1analyzer.add_marker()

########################################################################################################################
    def on_CentralFreq_input(self):
        # Vérification de l'éxistence de l'attribut après suppression
        if not hasattr(self, 'Rx0analyzer') or not hasattr(self, 'Rx1analyzer'):
            self.log("Impossible de changer la fréquence centrale: aucun Spectrum Analyzer disponible", color='red')
            return

        # Récupérer le contenu de l'input centralFreq
        central_freq = int(self.CentralFreq_input.text())

        # Changer la fréquence centrale du Spectrum Analyzer
        self.ad9363_bis.rx_lo = int(central_freq * 1e6)

########################################################################################################################
############################################ TAB AD9363 monitoring #####################################################
########################################################################################################################

    # Routine pour monitorer les paramètres de l'AD9363
    def monitoring(self):

        if hasattr(self, 'ad9363'):

            # Puissance RSSI:
            # Mise à jour du texte RSSI_Rx0_output avec arrondi à deux chiffres après la virgule
            # rssi_rx0_value = float(str(self.ad9363._get_rx0_rssi()).replace(' dB', '')) - self.Rx0_cal
            # rssi_rx1_value = float(str(self.ad9363._get_rx0_rssi()).replace(' dB', '')) - self.Rx1_cal

            # self.RSSI_Rx0_output.setText(f"{round(rssi_rx0_value, 2)} dBm")
            # self.RSSI_Rx1_output.setText(f"{round(rssi_rx1_value, 2)} dBm")

            # self.RSSI_Rx0_output.setText(self.ad9363._get_rx0_rssi())
            # self.RSSI_Rx1_output.setText(self.ad9363._get_rx1_rssi())
            # self.RSSI_Tx0_output.setText(self.ad9363._get_tx0_rssi())
            # self.RSSI_Tx1_output.setText(self.ad9363._get_tx1_rssi())

            # Gain
            self.Rx0Gain_output.setText(str(self.ad9363._get_rx0_gain()) + " dB")
            self.Rx1Gain_output.setText(str(self.ad9363._get_rx1_gain()) + " dB")
            self.Tx0Gain_output.setText(str(self.ad9363._get_tx0_gain()) + " dB")
            self.Tx1Gain_output.setText(str(self.ad9363._get_tx1_gain()) + " dB")

            # Sampling
            self.ADCRate_output.setText(str(round(float(self.ad9363._get_txUpSampling()) / 1e6, 3)) + " MS/s")

            # LO
            self.TxLO_output.setText(str(round(float(self.ad9363._get_txLoFreq()), 2)) + " Mhz")
            self.RxLO_output.setText(str(round(float(self.ad9363._get_rxLoFreq()), 2)) + " Mhz")

            # BW (Il manque Rx1 et Tx1 !!!!!)
            self.TxBW_output.setText(str(round(float(self.ad9363._get_tx0BW()), 2)) + " Mhz")
            # self.TxBW_output.setText(str(round(float(self.ad9363._get_rx1BW()), 2)) + " Mhz")
            self.RxBW_output.setText(str(round(float(self.ad9363._get_rx0BW()), 2)) + " Mhz")
            # self.RxBW_output.setText(str(round(float(self.ad9363._get_tx1BW()), 2)) + " Mhz")

            # Sampling
            self.ADCBuffer_output.setText(str(self.ad9363_bis.rx_buffer_size) + " samples")

        else:
            # self.log("Veuillez d'abord vous connecter au PlutoSDR", color='red')
            return

    def on_TxLO_input(self):
        if hasattr(self, 'ad9363'):
            self.ad9363._set_txLoFreq(float(self.TxLO_input.text()))

    def on_RxLO_input(self):
        if hasattr(self, 'ad9363'):
            self.ad9363._set_rxLoFreq(float(self.RxLO_input.text()))
    def on_RxBW_input(self):
        if hasattr(self, 'ad9363'):
            self.ad9363._set_rxBW(rx0_value=float(self.RxBW_input.text()), rx1_value=float(self.RxBW_input.text()))
    def on_TxBW_input(self):
        if hasattr(self, 'ad9363'):
            self.ad9363._set_txBW(tx0_value=float(self.TxBW_input.text()), tx1_value=float(self.TxBW_input.text()))
    def on_ADCRate_input(self):
        if hasattr(self, 'ad9363'):
            print(self.ADCRate_input.text())
            self.ad9363_bis.sample_rate = float(self.ADCRate_input.text()) * 1e6
            self.Rx0analyzer.sampling_rate = float(self.ADCRate_input.text()) * 1e6
            self.Rx1analyzer.sampling_rate = float(self.ADCRate_input.text()) * 1e6
    def on_ADCBuffer_input(self):
        if hasattr(self, 'ad9363'):
            self.ad9363_bis.rx_buffer_size = int(self.ADCBuffer_input.text())
    def on_Rx0Gain_input(self):
        value = self.Rx0Gain_input.value()
        print(value)
        if hasattr(self, 'ad9363'):
            self.ad9363_bis.rx_hardwaregain_chan0 = int(value)
            self.Rx0Gain_output.setText(str(self.ad9363._get_rx0_gain()) + " dB")
    def on_Rx1Gain_input(self):
        value = self.Rx1Gain_input.value()
        print(value)
        if hasattr(self, 'ad9363'):
            self.ad9363_bis.rx_hardwaregain_chan1 = int(value)
            self.Rx1Gain_output.setText(str(self.ad9363._get_rx1_gain()) + " dB")
    def on_Tx0Gain_input(self):
        value = self.Tx0Gain_input.value()
        print(value)
        if hasattr(self, 'ad9363'):
            self.ad9363_bis.tx_hardwaregain_chan0 = int(value)
            self.Tx0Gain_output.setText(str(self.ad9363._get_tx0_gain()) + " dB")
    def on_Tx1Gain_input(self):
        if hasattr(self, 'ad9363'):
            value = self.Tx1Gain_input.value()
            print(value)
            self.ad9363_bis.tx_hardwaregain_chan1 = int(value)
            self.Tx1Gain_output.setText(str(self.ad9363._get_tx1_gain()) + " dB")

    def on_Rx1Gain_mode(self):
        if hasattr(self, 'ad9363'):
            self.ad9363_bis.gain_control_mode_chan1 = self.Rx1Gain_mode.currentText()
    def on_Rx0Gain_mode(self):
        if hasattr(self, 'ad9363'):
            self.ad9363_bis.gain_control_mode_chan0 = self.Rx0Gain_mode.currentText()

########################################################################################################################
################################################# TAB Phase Shift ######################################################
########################################################################################################################
    def on_AoA_ready(self, angle):

        # Lorsque le thread DSP (Digital Signal Processing) transmet une nouvelle estimation du déphasage
        if hasattr(self, 'MonopulseAngleEstimator'):

            # Récupérer plutôt la moyenne que le déphasage courant
            if self.AveragingEnabled and self.MonopulseAngleEstimator.get_average() is not None:
                angle = self.MonopulseAngleEstimator.get_average()

            self.GraphicalDOA.updateDATA(angle)
            self.GraphicalDOA.p1.setTitle(str(round(angle, 3)) + " °")
            self.PhaseCalibration_output.setText(str(self.MonopulseAngleEstimator.phase_cal) + " °")

    def on_phase_calibrationButton_click(self):
        if hasattr(self, 'MonopulseAngleEstimator'):

            # Émettre le signal pour réinitialiser la calibration
            self.MonopulseAngleEstimator.reset_calibration_signal.emit()

    def onPhaseStep_click(self):
        if hasattr(self, 'MonopulseAngleEstimator'):

            self.MonopulseAngleEstimator.update_parameters(step_deg=float(self.step_phase_input.text()))

    def onFcarrier_click(self):
        if hasattr(self, 'MonopulseAngleEstimator'):

            self.MonopulseAngleEstimator.update_parameters(F0=float(self.Fcarrier_input.text()))
    def onAveraging(self):

        if hasattr(self, 'MonopulseAngleEstimator'):

            # Si l'utilisateur sélectionne "ON" pour l'activation du moyennage
            if self.Averaging_input.currentText() == "ON":
                self.AveragingEnabled = True

            # Si l'utilisateur sélectionne "OFF" pour l'activation du moyennage
            if self.Averaging_input.currentText() == "OFF":
                self.AveragingEnabled = False

    def on_WindowSize_changed(self, value):
        self.MonopulseAngleEstimator.window_size = value

    """Méthode pour afficher un message dans le log"""
    def log(self, message, color='black'):
        # Utilisation de HTML pour définir la couleur du texte
        self.Log1.appendHtml(f"<span style='color: {color};'>{message}</span>")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MyGUI()
    window.show()
    sys.exit(app.exec_())
    sys.exit(app.exec_())