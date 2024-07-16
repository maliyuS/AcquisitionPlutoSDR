import csv
import sys
import datetime
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication, QTimer
from PlutoSetup import CustomSDR
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import os
import threading
class AcquisitionThread(QThread):
    data_received = pyqtSignal(object, object)

    def __init__(self, sdr, parent=None):
        super().__init__(parent)
        self.sdr = sdr

        # Initialiser la variable de classe qui contiendra les échantillons concaténés
        self.Rx0_combined_samples = np.array([], dtype=complex)
        self.Rx1_combined_samples = np.array([], dtype=complex)

        #Les variables d'état
        self._running = False
        self._scheduleSaving = False
        self._ImmediateSaving = False
        self._transmitting = False
        self._stopTransmitting = False

    """ La routine d'acquisition des données"""
########################################################################################################################
    def run(self):
        self._running = True
        self.sdr.calibrate_rx()
        while self._running:
            data = self.sdr.receive_data()
            self.data_received.emit(data['Rx_0'], data['Rx_1'])
            if self._scheduleSaving:
                self.append_samples(data['Rx_0'], data['Rx_1'])
                self.check_and_save_samples(max_size_bytes=500)
            if self._ImmediateSaving:
                self.save_IQSamples_to_csv(data['Rx_0'], data['Rx_1'])
                self._ImmediateSaving = False
            if self._transmitting:
                self.sdr.test_send_tx_data()
                self._transmitting = False
            if self._stopTransmitting:
                self.sdr.end_transmission()
                self._stopTransmitting = False


    def stop(self):
        self._running = False

########################################################################################################################

    """ Les fonctions pour enregistrer les données """

    def check_and_save_samples(self, max_size_bytes=500):
        """
        Vérifie si la taille combinée des échantillons Rx0 et Rx1 dépasse max_size_bytes.
        Si oui, sauvegarde les échantillons dans un fichier parquet et réinitialise les tableaux.

        Paramètre:
            max_size_bytes (int): Taille maximale autorisée en octets pour les échantillons combinés.
        """
        # Préparer les données à écrire
        combined_data = np.column_stack((np.real(self.Rx0_combined_samples), np.imag(self.Rx0_combined_samples), np.real(self.Rx1_combined_samples), np.imag(self.Rx1_combined_samples)))
        header = 'Rx0_I, Rx0_Q, Rx1_I, Rx1_Q'

        # Calculer la taille des échantillons combinés en bytes
        current_size = combined_data.nbytes / (1024 ** 2 * 15 / 50) #facteur de correction 15/50
        print(f"Taille des échantillons combinés: {current_size:.2f} Mo")

        if current_size > max_size_bytes:
            TimeStamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.save_IQSamples_to_parquet_thread(combined_data, header, TimeStamp)
            self.Rx0_combined_samples = np.array([], dtype=complex)
            self.Rx1_combined_samples = np.array([], dtype=complex)

########################################################################################################################
    def append_samples(self, Rx0, Rx1):
        """
        Concatène les échantillons des canaux Rx0 et Rx1 et les stocke dans des variables de classe distinctes.

        Paramètres:
            Rx0 (numpy.array): Un tableau numpy contenant les échantillons IQ complexes pour le canal Rx0 sous la forme (I + jQ).
            Rx1 (numpy.array): Un tableau numpy contenant les échantillons IQ complexes pour le canal Rx1 sous la forme (I + jQ).
        """

        # Stocker ou concaténer les échantillons de Rx0
        if self.Rx0_combined_samples.size == 0:
            self.Rx0_combined_samples = Rx0
        else:
            self.Rx0_combined_samples = np.concatenate((self.Rx0_combined_samples, Rx0))

        # Stocker ou concaténer les échantillons de Rx1
        if self.Rx1_combined_samples.size == 0:
            self.Rx1_combined_samples = Rx1
        else:
            self.Rx1_combined_samples = np.concatenate((self.Rx1_combined_samples, Rx1))

########################################################################################################################
    def save_IQSamples_to_parquet(self, combined_data, header, TimeStamp=None):
        """
        Sauvegarde les données d'un des canaux de réception du PlutoSDR au format Parquet.

        Paramètres:
            combined_data (numpy array): Un tableau numpy contenant les échantillons IQ complexes sous la forme (I + jQ).
            header (str): L'en-tête pour le fichier parquet.
            TimeStamp (str): Le timestamp pour nommer le fichier.
        """
        # Obtenir le répertoire de travail courant et définir le chemin complet
        current_directory = os.getcwd()
        folder_path = os.path.join(current_directory, "recordings_temp")

        # Filename à partir des conditions d'enregistrement (date,heure, channel)
        today = datetime.datetime.now().strftime("%d-%m-%Y")
        current_time = datetime.datetime.now().strftime("%Hh%Mm%Ss")
        filename = f"IQSamples_{today}_{current_time}.parquet"

        # Le chemin de sauvegarde complet
        complete_path = os.path.join(folder_path, filename)

        print(f"Enregistrement des signaux IQ à la date {TimeStamp}")

        # Créer le dossier contenant le fichier Parquet, s'il n'existe pas
        os.makedirs(os.path.dirname(complete_path), exist_ok=True)

        # Convertir les données en DataFrame pandas
        df = pd.DataFrame(combined_data, columns=header.split(', '))

        # Convertir le DataFrame pandas en table pyarrow
        table = pa.Table.from_pandas(df)

        # Écrire la table en format Parquet pour que ce soit plus rapide. Il faudra ensuite le décompresser pour le lire.
        pq.write_table(table, complete_path, use_dictionary=True, compression='snappy')

        print(f"Les échantillons IQ ont été enregistrés avec succès dans {complete_path}.")

########################################################################################################################
    def save_IQSamples_to_parquet_thread(self, combined_data, header, TimeStamp=None):
        # Créer et démarrer un thread pour exécuter save_IQSamples_to_parquet
        save_thread = threading.Thread(target=self.save_IQSamples_to_parquet, args=(combined_data, header, TimeStamp))
        save_thread.start()

########################################################################################################################
    def save_IQSamples_to_csv(self, data_rx0, data_rx1):
        """
        Sauvegarde les données des canaux de réception Rx_0 et Rx_1 du PlutoSDR au format CSV.

        Paramètres:
            data_rx0 (numpy array): Un tableau numpy contenant les échantillons IQ complexes sous la forme (I + jQ) pour le canal Rx_0.
            data_rx1 (numpy array): Un tableau numpy contenant les échantillons IQ complexes sous la forme (I + jQ) pour le canal Rx_1.
        """
        # Obtenir le répertoire de travail courant
        current_directory = os.getcwd()

        # Filename à partir des conditions d'enregistrement (date, heure)
        now = datetime.datetime.now()
        today = now.strftime("%d-%m-%Y")
        current_time = now.strftime("%Hh%Mm%Ss")
        filename = f"IQSamples_{today}_{current_time}.csv"

        # Répertoire pour enregistrer les échantillons
        recordings_dir = os.path.join(current_directory, "recordings_temp")
        complete_path = os.path.join(recordings_dir, filename)
        print(f"Enregistrement des signaux IQ dans {complete_path}")

        # Créer le dossier contenant le fichier CSV, s'il n'existe pas
        os.makedirs(recordings_dir, exist_ok=True)

        # Maintenant, ouvrir le fichier CSV
        with open(complete_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Rx0_I', 'Rx0_Q', 'Rx1_I', 'Rx1_Q'])  # En-tête du CSV

            # Parcourir les tableaux numpy des échantillons et les stocker dans le CSV
            for index in range(len(data_rx0)):
                rx0_sample = data_rx0[index]
                rx1_sample = data_rx1[index]

                rx0_i = np.real(rx0_sample)  # Partie réelle du nombre complexe pour Rx_0
                rx0_q = np.imag(rx0_sample)  # Partie imaginaire du nombre complexe pour Rx_0
                rx1_i = np.real(rx1_sample)  # Partie réelle du nombre complexe pour Rx_1
                rx1_q = np.imag(rx1_sample)  # Partie imaginaire du nombre complexe pour Rx_1

                writer.writerow([rx0_i, rx0_q, rx1_i, rx1_q])

########################################################################################################################
########################################################################################################################

# Exemple d'utilisation
def test_acquisition_thread():
    app = QCoreApplication(sys.argv)

    # Afficher que la connexion au Pluto à fonctionnée
    my_sdr = CustomSDR(uri='ip:192.168.2.1')
    my_sdr.configure_rx_properties()
    my_sdr.configure_tx_properties()
    my_sdr.configure_sampling_properties()

    # Initialiser le thread d'acquisition
    acquisition_thread = AcquisitionThread(my_sdr)

    # Définir un slot pour imprimer les données reçues
    def print_data(rx0, rx1):
        print("Data received:")
        print("Rx_0:", rx0)
        print("Rx_1:", rx1)

    # Connecter le signal data_received au slot print_data
    acquisition_thread.data_received.connect(print_data)

    # Démarrer le thread d'acquisition
    acquisition_thread.start()

    # Utiliser QTimer pour arrêter le thread après 5 secondes
    def stop_thread():
        acquisition_thread.stop()
        acquisition_thread.wait()
        print("Acquisition thread stopped.")
        QCoreApplication.quit()

    QTimer.singleShot(5000, stop_thread)

    # Exécuter application Qt
    sys.exit(app.exec_())

# Appeler la fonction de test
# test_acquisition_thread()