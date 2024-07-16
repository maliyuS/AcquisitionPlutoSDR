import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal


class MonopulseAngleEstimator(QThread):
    """Classe pour estimer l'angle de direction d'un signal reçu par un réseau d'antennes."""

    AoA_ready = pyqtSignal(object)  # Signal pour envoyer les résultats
    reset_calibration_signal = pyqtSignal()

    def __init__(self, step_deg=0.1, window_size=1, f0=2227e6, d_wavelength=0.5):

        super().__init__()

        # Valeurs actuelles des signaux reçus
        self.Rx_0 = None
        self.Rx_1 = None

        """ Moyennage """
        self.window_size = window_size  # Taille de la fenêtre pour le moyennage
        self.window_values = []  # Liste pour stocker les valeurs de la fenêtre

        """ RF """
        self.C = 3E8  # Vitesse de la lumière en mètres par seconde
        self.F0 = f0  # Fréquence de la porteuse RF
        self.d_wavelength = d_wavelength  # Distance entre les éléments du réseau d'antennes en portions de la longueurs d'onde. On utilise habituellement 0.5
        self.wavelength = self.C / self.F0  # Longueur d'onde de la porteuse RF
        self.d = self.d_wavelength * self.wavelength  # Distance (THEORIQUE!) entre les éléments du réseau d'antennes

        """ Echantillonnage """
        self.full_scale = 2 ** 11  # Pleine échelle pour l'ADC du PlutoSDR

        """ Calibration de phase """
        self.phase_cal = 0
        self.last_phase_delay = 0  # Dernier déphasage utilisé pour le suivi
        self.step_deg = step_deg  # Pas de déphasage pour la recherche de l'angle de direction
        # self.step_deg_cal = 0.1  # Pas de déphasage pour la calibration de phase
        self.step_deg_cal = 1  # Pas de déphasage pour la calibration de phase

        """ Variables d'état """
        self.calibrated = False  # Indique si la calibration de phase a été effectuée
        # self.new_data = False  # Indique si de nouveaux signaux sont disponibles

        # Connexion des signaux aux méthodes évenementiels
        self.reset_calibration_signal.connect(self.reset_calibration)

    def update_parameters(self, step_deg=None, window_size=None, f0=None):
        """ Met à jour les paramètres de la classe. """
        if step_deg is not None:
            self.step_deg = step_deg
        if window_size is not None:
            self.window_size = window_size
        if f0 is not None:
            self.F0 = f0

    ########################################################################################################################
    ########################################### Spectre de fréquence #######################################################
    ########################################################################################################################

    def fft(self, raw_data):
        """
        Convertit un tableau d'échantillons IQ en un spectre de fréquence.

        Paramètres:
        - raw_data (array): Tableau de données IQ complexes.

        Retourne:
        - s_dbfs (array): Spectre de fréquence.
        """
        # Nombre d'échantillons dans les données brutes
        NumSamples = len(raw_data)

        # Fenêtrage Hanning pour réduire les fuites spectrales
        win = np.hanning(NumSamples)

        # Application de la fenêtre aux données
        y = raw_data * win

        # Calcul de la FFT normalisée par la somme de la fenêtre
        s_fft = np.fft.fft(y) / np.sum(win)

        # Décalage zéro-fréquence au centre du spectre
        s_shift = np.fft.fftshift(s_fft)

        return s_shift

    def dbfs(self, s_shift):
        """
        Normalise un spectre par rapport à la pleine échelle (dBFS).

        Arguments:
        s_shift (array) : Spectre de fréquence complexe.

        Retourne:
        s_dbfs (array) : Spectre en dBFS.

        Note:
        Le PlutoSDR intègre un ADC qui quantifie les données sur 12 bits, donc la pleine échelle
        est considérée comme 2^11.
        """

        return 20 * np.log10(np.abs(s_shift) / self.full_scale)

    ########################################################################################################################
    ########################################### Estimation d'angle (Monopulse de Phase) ####################################
    ########################################################################################################################

    def calcTheta(self, deltaphase):
        """
        Calcule l'angle de direction (theta) pour un signal reçu par un réseau d'antennes,
        basé sur la différence de phase mesurée entre les antennes.

        Paramètres:
        - deltaphase : La différence de phase en degrés entre les signaux reçus par les antennes.
        - d : La distance entre les éléments du réseau d'antennes (en mètres).
        - rx_lo : La fréquence du signal reçu (en Hz).

        Retourne:
        - L'angle de direction theta en degrés.

        Formule utilisée:
        theta = arcsin(c * deltaphase / (2 * pi * f * d))
        où c est la vitesse de la lumière (approximativement 3E8 m/s).

        Remarques:
        - Le déphasage entre les deux signaux modulés est conservé après la démodulation,
          ce qui permet de mesurer le déphasage en bande de base.
        - La fréquence rx_lo est utilisée dans la formule pour calculer le retard
          qui s'est produit lorsque l'onde se propageait en espace libre.
        """

        # Conversion de la différence de phase de degrés en radians pour le calcul
        arcsin_arg = np.deg2rad(deltaphase) * self.C / (2 * np.pi * self.F0 * self.d)

        # Assurez-vous que l'argument pour arcsin reste entre -1 et 1 pour éviter les erreurs
        arcsin_arg = max(min(1, arcsin_arg), -1)

        # Calcul de l'angle theta en degrés à partir de l'argument arcsin
        calc_theta = np.rad2deg(np.arcsin(arcsin_arg))

        return calc_theta

    def monopulse_angle(self, array1, array2):
        ''' Correlate the sum and delta signals  '''
        # Since our signals are closely aligned in time, we can just return the 'valid' case where the signals completley overlap
        # We can do correlation in the time domain (probably faster) or the freq domain
        # In the time domain, it would just be this:
        # sum_delta_correlation = np.correlate(delayed_sum, delayed_delta, 'valid')
        # But I like the freq domain, because then I can focus just on the fc0 signal of interest

        sum_delta_correlation = np.correlate(array1, array2, 'valid')
        angle_diff = np.angle(sum_delta_correlation)

        return angle_diff

    def scan_for_DOA(self):

        # Initialisation des listes pour stocker les résultats des pics et des phases
        peak_sum = []
        peak_delta = []
        monopulse_phase = []

        # Création d'une plage de déphasages possibles, de -180 à 178 degrés par pas de 1 degrés
        delay_phases = np.arange(-180, 180, self.step_deg_cal)

        # Sauvegarde des signaux Rx_1 et Rx_0 pour éviter de corrompre les données originales
        Rx_1_temp = self.Rx_1
        Rx_0_temp = self.Rx_0

        for phase_delay in delay_phases:
            # Application du déphasage avec calibration au signal Rx_1
            delayed_Rx_1 = Rx_1_temp * np.exp(1j * np.deg2rad(phase_delay))

            # Calcul de la somme et de la différence des signaux
            delayed_sum = Rx_0_temp + delayed_Rx_1
            delayed_delta = Rx_0_temp - delayed_Rx_1

            # FFT des signaux sommés et différenciés
            delayed_sum_fft = self.fft(delayed_sum)
            delayed_delta_fft = self.fft(delayed_delta)

            # Conversion des spectres FFT en dBFS
            delayed_sum_dbfs = self.dbfs(delayed_sum_fft)
            delayed_delta_dbfs = self.dbfs(delayed_delta_fft)

            # Estimation de l'angle à partir de la corrélation des signaux sommés et différenciés
            mono_angle = self.monopulse_angle(delayed_sum, delayed_delta)

            peak_sum.append(np.max(delayed_sum_dbfs))
            peak_delta.append(np.max(delayed_delta_dbfs))
            monopulse_phase.append(np.sign(mono_angle))

        peak_dbfs = np.max(peak_sum)
        peak_delay_index = np.where(peak_sum == peak_dbfs)
        peak_delay = delay_phases[peak_delay_index[0][0]]
        steer_angle = int(self.calcTheta(peak_delay))

        return {'delay_phases': delay_phases,
                'peak_dbfs': peak_dbfs,
                'peak_delay': peak_delay,
                'steer_angle': steer_angle,
                'peak_sum': peak_sum,
                'peak_delta': peak_delta,
                'monopulse_phase': monopulse_phase
                }

    def tracking(self):

        # Application du déphasage avec calibration au signal Rx_1
        delayed_Rx_1 = self.Rx_1 * np.exp(1j * np.deg2rad(self.last_phase_delay + self.phase_cal))

        # Calcul de la somme et de la différence des signaux
        delayed_sum = self.Rx_0 + delayed_Rx_1
        delayed_delta = self.Rx_0 - delayed_Rx_1

        # FFT des signaux sommés et différenciés
        delayed_sum_fft = self.fft(delayed_sum)
        delayed_delta_fft = self.fft(delayed_delta)

        # Intercorrelation des cannaux somme et delta
        mono_angle = self.monopulse_angle(delayed_sum_fft, delayed_delta_fft)

        # Le signe de l'intercorrelation indique le sens du changement de phase
        if np.sign(mono_angle) > 0:
            self.last_phase_delay = self.last_phase_delay - self.step_deg
        else:
            self.last_phase_delay = self.last_phase_delay + self.step_deg
        return self.last_phase_delay

    def Autocal(self):

        self.phase_cal = self.scan_for_DOA()['peak_delay']
        self.calibrated = True

    ########################################################################################################################
    ################################################# Moyennage ############################################################
    ########################################################################################################################

    def add_sample(self, sample_value):
        """Ajoute un échantillon à la fenêtre et gère la taille de la fenêtre."""
        self.window_values.append(sample_value)

        # Si la nouvelle taille de la fenêtre est plus petite, supprimer les échantillons les plus anciens
        if len(self.window_values) > self.window_size:
            self.window_values = self.window_values[-self.window_size:]

    def is_window_full(self):
        """Vérifie si la fenêtre contient assez d'échantillons pour le calcul."""
        return len(self.window_values) == self.window_size

    def get_average(self):
        """Calcule la moyenne des valeurs de la fenêtre si elle est pleine."""
        if self.is_window_full():
            print(self.window_size)
            return sum(self.window_values) / len(self.window_values)
        return None  # Fenêtre pas encore pleine, pas de moyenne disponible

    def count_distinct_values(self):
        """Retourne le nombre de valeurs distinctes et leurs occurrences sous forme de tableau 2D."""
        value_counts = {}
        for value in self.window_values:
            if value in value_counts:
                value_counts[value] += 1
            else:
                value_counts[value] = 1
        # Convertir le dictionnaire en tableau 2D
        distinct_table = [[key, value] for key, value in value_counts.items()]
        return distinct_table

    ########################################################################################################################
    ################################################# Thread ###############################################################
    ########################################################################################################################
    def reset_calibration(self):
        """Méthode pour réinitialiser la calibration."""
        self.calibrated = False

    def set_new_data(self, Rx_0, Rx_1):
        """Mettre à jour les signaux reçus par le réseau d'antennes."""
        self.Rx_0 = Rx_0
        self.Rx_1 = Rx_1

    def run(self):
        """Fonction principale du thread pour l'estimation de l'angle de direction."""
        print("tata")
        while True:
            # Si les deux signaux reçus sont disponibles
            if self.Rx_0 is not None and self.Rx_1 is not None:

                # Si la calibration de phase n'a pas encore été effectuée
                if not self.calibrated:
                    self.phase_cal = 0
                    self.Autocal()

                # Suivre l'angle de direction
                self.tracking()

                # Envoyer le déphasage via le signal
                self.AoA_ready.emit(self.last_phase_delay)

                # Conserver le dernier déphasage dans la fenêtre mobile
                self.add_sample(self.last_phase_delay)
