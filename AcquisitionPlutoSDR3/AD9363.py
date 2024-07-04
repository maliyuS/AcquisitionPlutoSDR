"""
    Basic class to simplifiy interaction with pluto as an iio device
                                                            rgr12jan18
 * Copyright (C) 2018 Radio System Design Ltd.
 * Author: Richard G. Ranson, richard@radiosystemdesign.com
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation under
 * version 2.1 of the License.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
"""
# Sources:
# - https://github.com/radiosd/PlutoSdr/blob/master/pluto/pluto_sdr.py
# - https://wiki.gnuradio.org/index.php/PlutoSDR_Source

# basic class to simplifiy interaction with pluto as an iio device
from __future__ import print_function

import logging

import iio
import numpy as np

PLUTO_ID = 'ip:pluto.local'
NO_BITS = 12  # internal ADC and DAC width

# properties are in MHz, but the value set is a str
_M2Str = lambda x: str(int(x*1e6))          # convert MHz float to string in Hz


class AD9363(object):
    """Encapsulation of Pluto SDR device
       iio lib interface used to expose common functionality
       RF signal data read/write capabilities for rx and tx"""
    no_bits = NO_BITS
    TX_OFF = 0
    TX_DMA = 1
    TX_DDS = 2

    def __init__(self, uri=PLUTO_ID):
        # access to internal devices
        try:
            self.ctx = iio.Context(uri)
        except OSError:
            self.ctx = None
            print('exception: no iio device context found at', uri)
            return
        logging.debug('found context for pluto device')

        self.phy = self.ctx.find_device('ad9361-phy')

        # individual TRx controls
        self.phy_rx = self.phy.find_channel('voltage0', is_output=False)  # RX0

        # Cannaux RX
        self.phy_rx0 = self.phy.find_channel('voltage0', is_output=False) #HardwareGAIN + HardwareGAIN_MODE + RSSI RX0
        self.phy_rx1 = self.phy.find_channel('voltage1', is_output=False) #HardwareGAIN + HardwareGAIN_MODE + RSSI RX1

        # Cannaux TX
        self.phy_tx0 = self.phy.find_channel('voltage0', is_output=True) #HardwareGAIN + HardwareGAIN_MODE + RSSI TX0
        self.phy_tx1 = self.phy.find_channel('voltage1', is_output=True) #HardwareGAIN + HardwareGAIN_MODE + RSSI TX1

        # LOs
        self.phy_rx_LO = self.phy.find_channel('altvoltage0', is_output=True) # RXLO_powerdown + RXLO_frequency
        self.phy_tx_LO = self.phy.find_channel('altvoltage1', is_output=True) # TXLO_powerdown + TXLO_frequency

        # Sampling
        self.phy_rx_sampling = self.phy.find_channel('voltage', is_output=True) # Quadrature (bool) + RF DC Correction (bool) + BB DC Correction (bool)
        self.phy_tx_sampling = self.phy.find_channel('voltage', is_output=True)


        # access to data channels for Rx
        self.adc = self.ctx.find_device('cf-ad9361-lpc') # RX Sampling frequency
        # access to data channels for Tx
        self.dac = self.ctx.find_device('cf-ad9361-dds-core-lpc') # TX Sampling frequency



    # ---------------------- Receiver control-------------------------

                                    # RX_LO FREQ
    def _get_rxLoFreq(self):
        """get receiver LO frequency property in MHz"""
        value = self.phy_rx_LO.attrs['frequency'].value
        return int(value) / 1e6

    def _set_rxLoFreq(self, value):
        """set receiver LO frequency property in MHz"""
        self.phy_rx_LO.attrs['frequency'].value = _M2Str(value)

                                    # RXLO Powerdown (True/False)
    def _get_rxLoPowerdown(self):
        """get receiver LO powerdown property"""
        return self.phy_rx_LO.attrs['powerdown'].value

    def _set_rxLoPowerdown(self, value):
        """set receiver LO powerdown property"""
        self.phy_rx_LO.attrs['powerdown'].value = value

                                    # RF Bandwidth

    """Configures RX analog filters: RX TIA LPF and RX BB LPF. limits: >= 200000 and <= 52000000"""

    def _get_rx0BW(self):
        """get receiver analogue RF bandwidth in MHz"""
        value = self.phy_rx0.attrs['rf_bandwidth'].value
        return int(value) / 1e6
    def _get_rx1BW(self):
        """get receiver analogue RF bandwidth in MHz"""
        value = self.phy_rx1.attrs['rf_bandwidth'].value
        return int(value) / 1e6

    def _set_rxBW(self, rx0_value=None, rx1_value=None):
        if rx0_value is not None:
            self.phy_rx0.attrs['rf_bandwidth'].value = _M2Str(rx0_value)
        if rx1_value is not None:
            self.phy_rx1.attrs['rf_bandwidth'].value = _M2Str(rx1_value)

                                # GAIN
        "gain value, max of 71 dB, or 62 dB when over 4 GHz center freq"

        """Selects one of the available modes: manual, slow_attack, hybrid and fast_attack. 
            For most spectrum sensing type applications, use a manual gain, 
            so that you actually know when a signal is present or not, and it's relative power."""
        # Rx0

    def _get_rx0_gain(self):
        """read the rx RF gain in dB"""
        value = self.phy_rx0.attrs['hardwaregain'].value.split(' ')
        return float(value[0])

    def _get_rx0_gain_mode(self):
        """get the gain mode to one of those available"""
        return self.phy_rx0.attrs['gain_control_mode'].value

        # Rx1

    def _get_rx1_gain(self):
        """read the rx RF gain in dB"""
        value = self.phy_rx1.attrs['hardwaregain'].value.split(' ')
        return float(value[0])

    def _get_rx1_gain_mode(self):
        """get the gain mode to one of those available"""
        return self.phy_rx1.attrs['gain_control_mode'].value

    def _set_rx0_gain(self, valueRx0=None):
        """set the rx RF gain in dB or to auto, slow attack"""
        if valueRx0 is None:
            print('mode set to "slow_attack", other controls not yet available')
            self.phy_rx0.attrs['gain_control_mode'].value = 'slow_attack'
        else:
            self.phy_rx0.attrs['gain_control_mode'].value = 'manual'
            self.phy_rx0.attrs['hardwaregain'].value = '{:2.3f} dB'.format(valueRx0)

    # to set rx gain need to also control the gain mode
    def _set_rx_gain_mode(self, Rx0Value=None, Rx1Value=None):
        """set the gain mode to one of those available"""

        # Rx0:
        avail = self.phy_rx0.attrs['gain_control_mode_available'].value
        avail = avail.split()
        # allow setting with just the first letter
        _mode = '' if len(Rx0Value) == 0 else Rx0Value[0].upper()
        options = [av.capitalize()[0] for av in avail]
        if _mode in options:
            res = avail[options.index(_mode)]
            self.phy_rx0.attrs['gain_control_mode'].value = res
            logging.debug('gain mode set:', res)
        else:
            print('error: available modes are', avail)

        # Rx1:
        avail = self.phy_rx1.attrs['gain_control_mode_available'].value
        avail = avail.split()
        # allow setting with just the first letter
        _mode = '' if len(Rx1Value) == 0 else Rx1Value[0].upper()
        options = [av.capitalize()[0] for av in avail]
        if _mode in options:
            res = avail[options.index(_mode)]
            self.phy_rx1.attrs['gain_control_mode'].value = res
            logging.debug('gain mode set:', res)
        else:
            print('error: available modes are', avail)

                                    # RSSI
    def _get_rx0_rssi(self):
        """return rx rssi value"""  # this is 'ddd.dd dB'
        return self.phy_rx0.attrs['rssi'].value

    def _get_rx1_rssi(self):
        """return rx rssi value"""  # this is 'ddd.dd dB'
        return self.phy_rx1.attrs['rssi'].value


        # -------------------- Transmitter control------------------------

                                                # TXLO FREQ
    def _get_txLoFreq(self):
        """transmitter LO frequency property in MHz"""
        value = self.phy_tx_LO.attrs['frequency'].value
        return int(value) / 1e6

    def _set_txLoFreq(self, value):
        self.phy_tx_LO.attrs['frequency'].value = _M2Str(value)

                                                # TXLO Powerdown (True/False)
    def _get_txLoPowerdown(self):
        """get transmitter LO powerdown property"""
        return self.phy_tx_LO.attrs['powerdown'].value

    def _set_txLoPowerdown(self, value):
        """set transmitter LO powerdown property"""
        self.phy_tx_LO.attrs['powerdown'].value = value

                                                # GAIN
        "gain value, max of 71 dB, or 62 dB when over 4 GHz center freq"

        """Selects one of the available modes: manual, slow_attack, hybrid and fast_attack. 
            For most spectrum sensing type applications, use a manual gain, 
            so that you actually know when a signal is present or not, and it's relative power."""

    # Tx0
    def _get_tx0_gain(self):
        """get the tx RF gain in dB, it is always neg as an attenuation"""
        value = self.phy_tx0.attrs['hardwaregain'].value
        return float(value.split()[0])

    def _get_tx0_gain_mode(self):
        """get the gain mode to one of those available"""
        return self.phy_tx0.attrs['gain_control_mode'].value

    # Tx1
    def _get_tx1_gain(self):
        """get the tx RF gain in dB, it is always neg as an attenuation"""
        value = self.phy_tx1.attrs['hardwaregain'].value
        return float(value.split()[0])

    def _get_tx1_gain_mode(self):
        """get the gain mode to one of those available"""
        return self.phy_tx1.attrs['gain_control_mode'].value

    def _set_rx_gain_mode(self, Tx0Value=None, Tx1Value=None):
        """set the gain mode to one of those available"""

        # Tx0:
        avail = self.phy_tx0.attrs['gain_control_mode_available'].value
        avail = avail.split()
        # allow setting with just the first letter
        _mode = '' if len(Tx0Value) == 0 else Tx0Value[0].upper()
        options = [av.capitalize()[0] for av in avail]
        if _mode in options:
            res = avail[options.index(_mode)]
            self.phy_tx0.attrs['gain_control_mode'].value = res
            logging.debug('gain mode set:', res)
        else:
            print('error: available modes are', avail)

        # Rx1:
        avail = self.phy_tx1.attrs['gain_control_mode_available'].value
        avail = avail.split()
        # allow setting with just the first letter
        _mode = '' if len(Tx1Value) == 0 else Tx1Value[0].upper()
        options = [av.capitalize()[0] for av in avail]
        if _mode in options:
            res = avail[options.index(_mode)]
            self.phy_tx1.attrs['gain_control_mode'].value = res
            logging.debug('gain mode set:', res)
        else:
            print('error: available modes are', avail)

                                                    # RF Bandwidth
    def _get_tx0BW(self):
        """transmitter analogue RF bandwidth in MHz"""
        # available from channel [4] or [5] which are not named
        # iio-scope only changes [5], so use that
        value = self.phy_tx0.attrs['rf_bandwidth'].value
        return int(value) / 1e6

    def _get_tx1BW(self):
        """transmitter analogue RF bandwidth in MHz"""
        # available from channel [4] or [5] which are not named
        # iio-scope only changes [5], so use that
        value = self.phy_tx1.attrs['rf_bandwidth'].value
        return int(value) / 1e6

    def _set_txBW(self, tx0_value=None, tx1_value=None):
        if tx0_value is not None:
            self.phy_tx0.attrs['rf_bandwidth'].value = _M2Str(tx0_value)
        if tx1_value is not None:
            self.phy_tx1.attrs['rf_bandwidth'].value = _M2Str(tx1_value)

                                                    # RSSI
    def _get_tx0_rssi(self):
        """return tx rssi value"""
        return self.phy_tx0.attrs['rssi'].value

    def _get_tx1_rssi(self):
        """return tx rssi value"""
        return self.phy_tx1.attrs['rssi'].value


    # -------------------- Sampling control------------------------
    # (in_voltage_sampling_frequency) (outvoltage_sampling_frequency)

    # RX
    def _get_rxDownSampling(self):
        """control receiver output sampling frequency in MHz"""
        # only 2 options adc_rate or adc_rate/8
        _adc = self.adc.channels[0].attrs
        value = _adc['sampling_frequency'].value
        return value
    def _set_rxDownSampling(self, value):
        """control receiver output sampling frequency in MHz"""
        # only 2 options adc_rate or adc_rate/8
        _adc = self.adc.channels[0].attrs
        options = _adc['sampling_frequency_available'].value.split(' ')
        if value in options:
            _adc['sampling_frequency'].value = value
        else:
            print('error: available options are', options)

    # TX
    def _get_txUpSampling(self):
        """control transmitter output sampling frequency in MHz"""
        # only 2 options dac_rate or dac_rate/8
        _dac = self.dac.channels[0].attrs
        value = _dac['sampling_frequency'].value
        return value

    def _set_txUpSampling(self, value):
        """control transmitter output sampling frequency in MHz"""

        self.dac.channels[0].attrs['sampling_frequency'].value = value



    # ---------------------- SDR's Corrections --------------------------------

    # Quadrature (in_voltage_quadrature_tracking_en)
    # True/False
    def _get_rx0_quadrature(self):
        """return quadrature tracking"""
        return self.phy_rx0.attrs['quadrature_tracking_en'].value
    def _get_rx1_quadrature(self):
        """return quadrature tracking"""
        return self.phy_rx1.attrs['quadrature_tracking_en'].value

    def _set_quadrature(self, rx0Bool, rx1Bool):
        """set quadrature tracking"""
        if rx0Bool is bool :
            self.phy_rx0.attrs['quadrature_tracking_en'].value = rx0Bool
        if rx1Bool is bool :
            self.phy_rx1.attrs['quadrature_tracking_en'].value = rx1Bool

    # RF DC Correction Offset (in_voltage_rf_dc_offset_tracking_en)
    # True/False
    def _get_rx0_rf_dc_offset(self):
        """return RF DC offset tracking"""
        return self.phy_rx0.attrs['rf_dc_offset_tracking_en'].value
    def _get_rx1_rf_dc_offset(self):
        """return RF DC offset tracking"""
        return self.phy_rx1.attrs['rf_dc_offset_tracking_en'].value
    def _set_rf_dc_offset(self, rx0Bool, rx1Bool):
        """set RF DC offset tracking"""
        if rx0Bool is bool:
            self.phy_rx0.attrs['rf_dc_offset_tracking_en'].value = rx0Bool
        if rx1Bool is bool:
            self.phy_rx1.attrs['rf_dc_offset_tracking_en'].value = rx1Bool

    # BB DC Correction (in_voltage_bb_dc_offset_tracking_en)
    # True/False
    def _get_rx0_bb_dc_offset(self):
        """return BB DC offset tracking"""
        return self.phy_rx0.attrs['bb_dc_offset_tracking_en'].value
    def _get_rx1_bb_dc_offset(self):
        """return BB DC offset tracking"""
        return self.phy_rx1.attrs['bb_dc_offset_tracking_en'].value

    def _set_bb_dc_offset(self, rx0Bool, rx1Bool):
        """set BB DC offset tracking"""
        if rx0Bool is bool:
            self.phy_rx0.attrs['bb_dc_offset_tracking_en'].value = rx0Bool
        if rx1Bool is bool:
            self.phy_rx1.attrs['bb_dc_offset_tracking_en'].value = rx1Bool


def main():

    # create an instance of the class
    ad9363 = AD9363('ip:192.168.2.1')

    print("Puissances RSSI")
    print("RX0", ad9363._get_rx0_rssi())
    print("RX1", ad9363._get_rx1_rssi())
    print("TX0", ad9363._get_tx0_rssi())
    print("TX1", ad9363._get_tx1_rssi())

    print("Gain Control")
    # Rx0
    print ("RX0", ad9363._get_rx0_gain())
    print ("Mode", ad9363._get_rx0_gain_mode())
    # Rx1
    print ("RX1", ad9363._get_rx1_gain())
    print ("Mode", ad9363._get_rx1_gain_mode())

    # Tx0
    print ("TX0", ad9363._get_tx0_gain())
    # print ("Mode", ad9363._get_tx0_gain_mode()) pas possible, pas défini

    # Tx1
    print ("TX1", ad9363._get_tx1_gain())
    #print ("Mode", ad9363._get_tx1_gain_mode()) pas possible, pas défini

    print ("Frequencies")
    # LO FREQ
    print ("RX LO", ad9363._get_rxLoFreq())
    print ("TX LO", ad9363._get_txLoFreq())

    # BW
    print("RX0 BW", ad9363._get_rx0BW())
    print("RX1 BW", ad9363._get_rx1BW())
    print("TX0 BW", ad9363._get_tx0BW())
    print("TX1 BW", ad9363._get_tx1BW())

    # Powerdown
    print("RX LO Powerdown", ad9363._get_rxLoPowerdown())
    print("TX LO Powerdown", ad9363._get_txLoPowerdown())

    # Sampling
    print("RX Sampling", ad9363._get_rxDownSampling())
    print("TX Sampling", ad9363._get_txUpSampling())

    # Corrections
    # RX0
    print("RX0 Quadrature", ad9363._get_rx0_quadrature())
    print("RX0 RF DC Offset", ad9363._get_rx0_rf_dc_offset())
    print("BB DC Offset", ad9363._get_rx0_bb_dc_offset())

    # RX1
    print("RX1 Quadrature", ad9363._get_rx1_quadrature())
    print("RX1 RF DC Offset", ad9363._get_rx1_rf_dc_offset())
    print("BB DC Offset", ad9363._get_rx1_bb_dc_offset())

#main()

def test_unitaire():
    ad9363 = AD9363('ip:192.168.2.1')

    # Récupération des valeurs de gain
    rx0_gain_mode = ad9363._get_rx0_gain_mode()
    print(rx0_gain_mode)

test_unitaire()