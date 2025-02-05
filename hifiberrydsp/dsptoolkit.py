#!/usr/bin/env python3

'''
Copyright (c) 2018 Modul 9/HiFiBerry

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
import logging
import argparse
import os
import time
import sys
import urllib.request
import socket

try:
    from zeroconf import Zeroconf, ServiceBrowser
    zeroconf_enabled = True
except:
    zeroconf_enabled = False


from hifiberrydsp.hardware.adau145x import Adau145x
from hifiberrydsp.client.sigmatcp import SigmaTCPClient
from hifiberrydsp.filtering.biquad import Biquad
from hifiberrydsp.filtering.volume import decibel2amplification, \
    percent2amplification, amplification2decibel, amplification2percent
from hifiberrydsp.datatools import parse_int
from hifiberrydsp.parser.xmlprofile import  \
    ATTRIBUTE_VOL_CTL, ATTRIBUTE_VOL_LIMIT, \
    ATTRIBUTE_BALANCE, ATTRIBUTE_SAMPLERATE, \
    ATTRIBUTE_IIR_FILTER_LEFT, ATTRIBUTE_IIR_FILTER_RIGHT, \
    ATTRIBUTE_FIR_FILTER_LEFT, ATTRIBUTE_FIR_FILTER_RIGHT, \
    ATTRIBUTE_MUTE_REG, REGISTER_ATTRIBUTES, XmlProfile
from hifiberrydsp.server.constants import COMMAND_PROGMEM, \
    COMMAND_PROGMEM_RESPONSE, COMMAND_XML, COMMAND_XML_RESPONSE, \
    COMMAND_STORE_DATA, COMMAND_RESTORE_DATA, \
    COMMAND_DATAMEM, COMMAND_DATAMEM_RESPONSE, \
    COMMAND_GPIO, COMMAND_GPIO_RESPONSE, \
    GPIO_READ, GPIO_WRITE, GPIO_RESET, GPIO_SELFBOOT, \
    ZEROCONF_TYPE
from hifiberrydsp.parser.settings import SettingsFile

from hifiberrydsp import datatools
import hifiberrydsp


MODE_BOTH = 0
MODE_LEFT = 1
MODE_RIGHT = 2

DISPLAY_FLOAT = 0
DISPLAY_INT = 1
DISPLAY_HEX = 2
DISPLAY_BIN = 2

GLOBAL_REGISTER_FILE = "/etc/dspparameter.dat"
GLOBAL_PROGRAM_FILE = "/etc/dspprogram.xml"


class REW():

    def __init__(self):
        pass

    @staticmethod
    def readfilters(filename, fs=48000):
        filters = []

        with open(filename) as file:
            for line in file.readlines():
                if line.startswith("Filter"):
                    parts = line.split()
                    if len(parts) >= 12 and parts[2] == "ON" and \
                            parts[3] == "PK" and \
                            parts[4] == "Fc" and parts[6] == "Hz" and \
                            parts[7] == "Gain" and parts[9] == "dB" and \
                            parts[10] == "Q":

                        fc = float(parts[5])
                        gain = float(parts[8])
                        q = float(parts[11])
                        logging.info("Filter EQ fc=%s, q=%s, gaion=%s, fs=%s",
                                     fc, q, gain, fs)
                        filters.append(
                            Biquad.peaking_eq(fc, q, gain, fs))
                    elif len(parts) >= 6 and parts[2] == "ON" and \
                            parts[3] == "LP" and \
                            parts[4] == "Fc" and parts[6] == "Hz":

                        fc = float(parts[5])
                        logging.info("Filter LP fc=%s", fc)
                        filters.append(
                            Biquad.low_pass(fc, 0.707, fs))
                    elif len(parts) >= 9 and parts[2] == "ON" and \
                            parts[3] == "LPQ" and \
                            parts[4] == "Fc" and parts[6] == "Hz" and \
                            parts[7] == "Q":
                        fc = float(parts[5])
                        q = float(parts[8])
                        logging.info("Filter LPQ fc=%s, q=%s", fc, q)
                        filters.append(
                            Biquad.low_pass(fc, q, fs))
                    elif len(parts) >= 10 and parts[2] == "ON" and \
                            parts[3] == "LS" and \
                            parts[4] == "Fc" and parts[6] == "Hz" and \
                            parts[7] == "Gain" and parts[9] == "dB":
                        fc = float(parts[5])
                        db = float(parts[8])
                        q = 0.707
                        logging.info("Filter LS fc=%s, db=%s", fc, db)
                        filters.append(
                            Biquad.low_shelf(fc, q, db, fs))
                    elif len(parts) >= 6 and parts[2] == "ON" and \
                            parts[3] == "HP" and \
                            parts[4] == "Fc" and parts[6] == "Hz":

                        fc = float(parts[5])
                        logging.info("Filter HP fc=%s", fc)
                        filters.append(
                            Biquad.high_pass(fc, 0.707, fs))
                    elif len(parts) >= 9 and parts[2] == "ON" and \
                            parts[3] == "HPQ" and \
                            parts[4] == "Fc" and parts[6] == "Hz" and \
                            parts[7] == "Q":
                        fc = float(parts[5])
                        q = float(parts[8])
                        logging.info("Filter HPQ fc=%s, q=%s", fc, q)
                        filters.append(
                            Biquad.high_pass(fc, q, fs))
                    elif len(parts) >= 10 and parts[2] == "ON" and \
                            parts[3] == "HS" and \
                            parts[4] == "Fc" and parts[6] == "Hz" and \
                            parts[7] == "Gain" and parts[9] == "dB":
                        fc = float(parts[5])
                        db = float(parts[8])
                        q = 0.707
                        logging.info("Filter HS fc=%s, db=%s", fc, db)
                        filters.append(
                            Biquad.high_shelf(fc, q, db, fs))
                    elif len(parts) >= 7 and parts[2] == "ON" and \
                            parts[3] == "NO" and \
                            parts[4] == "Fc" and parts[6] == "Hz":
                        fc = float(parts[5])
                        q = 0.707
                        logging.info("Filter NO fc=%s", fc, db)
                        filters.append(
                            Biquad.notch(fc, q, fs))

                    else:
                        if len(parts) >= 4 and parts[3] != "None":
                            print("Filter type " + parts[3] +
                                  " not yet supported")

            return filters


class DSPError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class DSPToolkit():

    def __init__(self,
                 ip="127.0.0.1",
                 dsp=Adau145x()):
        self.dsp = dsp
        self.ip = ip
        self.sigmatcp = SigmaTCPClient(self.dsp, self.ip)
        self.resetgpio = None

    def set_ip(self, ip):
        self.ip = ip
        self.sigmatcp = SigmaTCPClient(self.dsp, self.ip)

    def set_volume(self, volume):
        volctl = datatools.parse_int(
            self.sigmatcp.request_metadata(ATTRIBUTE_VOL_CTL))

        if volctl is not None:
            self.sigmatcp.write_decimal(volctl, volume)
            return True
        else:
            logging.info("%s is undefined", ATTRIBUTE_VOL_CTL)
            return False

    def set_limit(self, volume):
        volctl = datatools.parse_int(
            self.sigmatcp.request_metadata(ATTRIBUTE_VOL_LIMIT))

        if volctl is not None:
            self.sigmatcp.write_decimal(volctl, volume)
            return True
        else:
            logging.info("%s is undefined", ATTRIBUTE_VOL_LIMIT)
            return False

    def get_volume(self):
        volctl = None
        try:
            volctl = datatools.parse_int(
                self.sigmatcp.request_metadata(ATTRIBUTE_VOL_CTL))
        except:
            pass

        if volctl is not None:
            return self.sigmatcp.read_decimal(volctl)
        else:
            logging.info("%s is undefined", ATTRIBUTE_VOL_CTL)

    def get_limit(self):
        volctl = datatools.parse_int(
            self.sigmatcp.request_metadata(ATTRIBUTE_VOL_LIMIT))

        if volctl:
            return self.sigmatcp.read_decimal(volctl)
        else:
            logging.info("%s is undefined", ATTRIBUTE_VOL_LIMIT)

    def set_balance(self, value):
        '''
        Sets the balance of left/right channels.
        Value ranges from 0 (only left channel) to 2 (only right channel)
        at balance=1 the volume setting on both channels is equal
        '''
        if (value < 0) or (value > 2):
            raise RuntimeError("Balance value must be between 0 and 2")

        balctl = datatools.parse_int(
            self.sigmatcp.request_metadata(ATTRIBUTE_BALANCE))

        if balctl is not None:
            self.sigmatcp.write_decimal(balctl, value)

    def write_biquad(self, addr, bq_params):
        self.sigmatcp.write_biquad(addr, bq_params)

    def write_fir(self, coefficients, mode=MODE_BOTH):

        (firleft, len_left) = datatools.parse_int_length(
            self.sigmatcp.request_metadata(ATTRIBUTE_FIR_FILTER_LEFT))
        (firright, len_right) = datatools.parse_int_length(
            self.sigmatcp.request_metadata(ATTRIBUTE_FIR_FILTER_RIGHT))

        if mode == MODE_BOTH or mode == MODE_LEFT:
            result = self.write_coefficients(firleft,
                                             len_left,
                                             coefficients)

        if mode == MODE_BOTH or mode == MODE_RIGHT:
            result = self.write_coefficients(firright,
                                             len_right,
                                             coefficients)

        return result

    def write_coefficients(self, addr, length, coefficients):
        if len(coefficients) > length:
            logging.error("can't deploy coefficients %s > %s",
                          len(coefficients), length)
            return False

        data = []
        for coeff in coefficients:
            x = list(self.sigmatcp.get_decimal_repr(coeff))
            data[0:0] = x

        x = list(self.sigmatcp.get_decimal_repr(0))
        for _i in range(len(coefficients), length):
            data[0:0] = x

        self.sigmatcp.write_memory(addr, data)

        return True

    def get_checksum(self):
        return self.sigmatcp.program_checksum()

    def generic_request(self, request_code, response_code=None):
        return self.sigmatcp.request_generic(request_code, response_code)

    def set_filters(self, filters, mode=MODE_BOTH, cutoff_long=False):

        (addr_left, length_left) = datatools.parse_int_length(
            self.sigmatcp.request_metadata(ATTRIBUTE_IIR_FILTER_LEFT))
        (addr_right, length_right) = datatools.parse_int_length(
            self.sigmatcp.request_metadata(ATTRIBUTE_IIR_FILTER_RIGHT))

        if mode == MODE_LEFT:
            maxlen = length_left
        elif mode == MODE_RIGHT:
            maxlen = length_right
        else:
            maxlen = min(length_left, length_right)

        assert maxlen % 5 == 0

        maxlen = maxlen / 5

        if len(filters) > maxlen and (cutoff_long == False):
            raise(DSPError("{} filters given, but filter bank has only {} slots".format(
                len(filters), maxlen)))

        self.hibernate(True)

        logging.debug("deploying filters %s", filters)

        i = 0
        for f in filters:
            logging.debug(f)
            if mode == MODE_LEFT or mode == MODE_BOTH:
                if i < length_left:
                    self.sigmatcp.write_biquad(addr_left + i * 5, f)
            if mode == MODE_RIGHT or mode == MODE_BOTH:
                if i < length_right:
                    self.sigmatcp.write_biquad(addr_right + i * 5, f)
            i += 1
            if i > maxlen:
                break

        self.hibernate(False)

    def clear_iir_filters(self, mode=MODE_BOTH):
        # Simply fill filter arrays with dummy filters
        self.set_filters([Biquad.plain()] * 256,
                         mode=mode, cutoff_long=True)

    def install_profile(self, xmlfile):
        return self.sigmatcp.write_eeprom_from_file(xmlfile)

    def install_profile_from_content(self, content):
        return self.sigmatcp.write_eeprom_from_xml(content)

    def mute(self, mute=True):
        mutereg = datatools.parse_int(
            self.sigmatcp.request_metadata(ATTRIBUTE_MUTE_REG))

        if mutereg is not None:
            if mute:
                self.sigmatcp.write_memory(
                    mutereg, self.sigmatcp.int_data(1))
            else:
                self.sigmatcp.write_memory(
                    mutereg, self.sigmatcp.int_data(0))
            return True
        else:
            return False

    def reset(self):
        self.sigmatcp.reset()

    def hibernate(self, hibernate=True):
        self.sigmatcp.hibernate(hibernate)
        time.sleep(0.001)

    def get_meta(self, attribute):
        return self.sigmatcp.request_metadata(attribute)

    def get_samplerate(self):
        sr = datatools.parse_int(
            self.sigmatcp.request_metadata(ATTRIBUTE_SAMPLERATE))

        if sr is None or sr == 0:
            return 48000
        else:
            return sr


class CommandLine():

    def __init__(self):
        self.command_map = {
            "save":  self.cmd_save,
            "load": self.cmd_load,
            "install-profile": self.cmd_install_profile,
            "set-volume": self.cmd_set_volume,
            "get-volume": self.cmd_get_volume,
            "set-limit": self.cmd_set_limit,
            "get-limit": self.cmd_get_limit,
            "apply-rew-filters": self.cmd_set_rew_filters,
            "apply-rew-filters-left": self.cmd_set_rew_filters_left,
            "apply-rew-filters-right": self.cmd_set_rew_filters_right,
            "apply-fir-filters": self.cmd_set_fir_filters,
            "apply-fir-filter-right": self.cmd_set_fir_filter_right,
            "apply-fir-filter-left": self.cmd_set_fir_filter_left,
            "clear-iir-filters": self.cmd_clear_iir_filters,
            "reset": self.cmd_reset,
            "read-dec": self.cmd_read,
            "loop-read-dec": self.cmd_loop_read_dec,
            "read-int": self.cmd_read_int,
            "loop-read-int": self.cmd_loop_read_int,
            "read-hex": self.cmd_read_hex,
            "loop-read-hex": self.cmd_loop_read_hex,
            "read-reg": self.cmd_read_reg,
            "loop-read-reg": self.cmd_loop_read_reg,
            "get-checksum": self.cmd_checksum,
            "write-reg": self.cmd_write_reg,
            "write-mem": self.cmd_write_mem,
            "get-xml": self.cmd_get_xml,
            "get-prog": self.cmd_get_prog,
            "get-meta": self.cmd_get_meta,
            "mute": self.cmd_mute,
            "unmute": self.cmd_unmute,
            "get-samplerate": self.cmd_samplerate,
            "check-eeprom": self.cmd_check_eeprom,
            "servers": self.cmd_servers,
            "apply-settings": self.cmd_apply_settings,
            "store-settings": self.cmd_store_settings,
            "store-filters": self.cmd_store_filters,
            "store": self.cmd_store,
            "version": self.cmd_version,
            "get-memory": self.cmd_get_memory,
            #            "selfboot": self.cmd_selfboot,
        }
        self.dsptk = DSPToolkit()

    def register_file(self):
        return os.path.expanduser("~/.dsptoolkit/registers.dat")

    def string_to_volume(self, strval):
        strval = strval.lower()
        vol = 0
        if strval.endswith("db"):
            try:
                dbval = float(strval[0:-2])
                vol = decibel2amplification(dbval)
            except:
                logging.error("Can't parse db value {}", strval)
                return None
            # TODO
        elif strval.endswith("%"):
            try:
                pval = float(strval[0:-1])
                vol = percent2amplification(pval)
            except:
                logging.error("Can't parse db value {}", strval)
                return None
        else:
            vol = float(strval)

        return vol

    def cmd_version(self):
        print(hifiberrydsp.__version__)

    def cmd_set_volume(self):
        if len(self.args.parameters) > 0:
            vol = self.string_to_volume(self.args.parameters[0])
        else:
            print("Volume parameter missing")
            sys.exit(1)

        if vol is not None:
            if self.dsptk.set_volume(vol):
                print("Volume set to {}dB".format(
                    amplification2decibel(vol)))
            else:
                print("Profile doesn't support volume control")
                sys.exit(1)

    def cmd_set_limit(self):
        if len(self.args.parameters) > 0:
            vol = self.string_to_volume(self.args.parameters[0])
        else:
            print("Volume parameter missing")
            sys.exit(1)

        if vol is not None:
            if self.dsptk.set_limit(vol):
                print("Limit set to {}dB".format(
                    amplification2decibel(vol)))
            else:
                print("Profile doesn't support volume control")
                sys.exit(1)

    def cmd_get_volume(self):
        vol = self.dsptk.get_volume()
        if vol is not None:
            print("Volume: {:.4f} / {:.0f}% / {:.0f}db".format(
                vol,
                amplification2percent(vol),
                amplification2decibel(vol)))
        else:
            print("Profile doesn't support volume control")
            sys.exit(1)

    def cmd_get_limit(self):
        vol = self.dsptk.get_limit()
        if vol is not None:
            print("Limit: {:.4f} / {:.0f}% / {:.0f}db".format(
                vol,
                amplification2percent(vol),
                amplification2decibel(vol)))
        else:
            print("Profile doesn't support volume limit")
            sys.exit(1)

    def cmd_read(self, display=DISPLAY_FLOAT, loop=False, length=None):
        try:
            addr = parse_int(self.args.parameters[0])
        except:
            print("Can't parse address {}".format(self.args.parameters))
            sys.exit(1)

        while True:
            if display == DISPLAY_FLOAT:
                val = self.dsptk.sigmatcp.read_decimal(addr)
                print("{:.8f}".format(val))
            elif display == DISPLAY_INT:
                val = 0
                for i in self.dsptk.sigmatcp.read_data(addr, length):
                    val *= 256
                    val += i
                print(val)
            elif display == DISPLAY_HEX:
                val = self.dsptk.sigmatcp.read_data(addr, length)
                print(''.join(["%02X " % x for x in val]))

            if not loop:
                break

            try:
                time.sleep(float(self.args.delay) / 1000)
            except KeyboardInterrupt:
                break

    def cmd_loop_read_dec(self):
        self.cmd_read(DISPLAY_FLOAT, True)

    def cmd_read_int(self):
        self.cmd_read(DISPLAY_INT, False)

    def cmd_loop_read_int(self):
        self.cmd_read(DISPLAY_INT, True)

    def cmd_read_hex(self):
        self.cmd_read(DISPLAY_HEX, False)

    def cmd_loop_read_hex(self):
        self.cmd_read(DISPLAY_HEX, True)

    def cmd_read_reg(self):
        self.cmd_read(DISPLAY_HEX,
                      False,
                      self.dsptk.dsp.REGISTER_WORD_LENGTH)

    def cmd_loop_read_reg(self):
        self.cmd_read(DISPLAY_HEX,
                      True,
                      self.dsptk.dsp.REGISTER_WORD_LENGTH)

    def cmd_reset(self):
        self.dsptk.reset()
        print("Resetting DSP")

    def cmd_clear_iir_filters(self):
        self.dsptk.clear_iir_filters(MODE_BOTH)
        print("Filters removed")

    def cmd_set_rew_filters(self, mode=MODE_BOTH):
        if len(self.args.parameters) == 0:
            print("Missing filename argument")
            sys.exit(1)

        filters = REW.readfilters(self.args.parameters[0],
                                  self.dsptk.get_samplerate())

        self.dsptk.clear_iir_filters(mode)
        try:
            self.dsptk.set_filters(filters, mode)
            print("Filters configured on both channels:")
            for f in filters:
                print(f.description)
        except DSPError as e:
            print(e)

    def cmd_set_rew_filters_left(self):
        self.cmd_set_rew_filters(mode=MODE_LEFT)

    def cmd_set_rew_filters_right(self):
        self.cmd_set_rew_filters(mode=MODE_RIGHT)

    def cmd_set_fir_filters(self, mode=MODE_BOTH):
        if len(self.args.parameters) > 0:
            filename = self.args.parameters[0]
        else:
            print("FIR filename missing")
            sys.exit(1)

        coefficients = []
        try:
            with open(filename) as firfile:
                for line in firfile:
                    coeff = float(line)
                    coefficients.append(coeff)
                    print(coeff)
        except Exception as e:
            print("can't read filter file (%s)", e)

        self.dsptk.hibernate(True)
        if self.dsptk.write_fir(coefficients, mode):
            print("deployed filters")
        else:
            print("can't deploy FIR filters "
                  "(not FIR filter in profile or filters in file too long)")
        self.dsptk.hibernate(False)

    def cmd_set_fir_filter_left(self):
        self.cmd_set_fir_filters(MODE_LEFT)

    def cmd_set_fir_filter_right(self):
        self.cmd_set_fir_filters(MODE_RIGHT)

    def cmd_checksum(self):
        checksum = self.dsptk.sigmatcp.program_checksum()

        print(''.join(["%02X" % x for x in checksum]))

    def cmd_get_xml(self):
        xml = self.dsptk.generic_request(COMMAND_XML,
                                         COMMAND_XML_RESPONSE)
        print(xml.decode("utf-8", errors="replace"))

    def cmd_get_prog(self):
        mem = self.dsptk.generic_request(COMMAND_PROGMEM,
                                         COMMAND_PROGMEM_RESPONSE)
        print(mem.decode("utf-8", errors="replace"))

    def cmd_get_Data(self):
        mem = self.dsptk.generic_request(COMMAND_DATAMEM,
                                         COMMAND_DATAMEM_RESPONSE)
        print(mem.decode("utf-8", errors="replace"))

    def cmd_get_meta(self):
        if len(self.args.parameters) > 0:
            attribute = self.args.parameters[0]
        value = self.dsptk.sigmatcp.request_metadata(attribute)
        print(value)

    def cmd_mute(self):
        if self.dsptk.mute(True):
            print("Muted")
        else:
            print("Mute not supported")

    def cmd_unmute(self):
        if self.dsptk.mute(False):
            print("Unmuted")
        else:
            print("Mute not supported")

    def cmd_save(self):
        self.dsptk.generic_request(COMMAND_STORE_DATA)

    def cmd_load(self):
        self.dsptk.generic_request(COMMAND_RESTORE_DATA)

    def cmd_samplerate(self):
        print("{}Hz".format(self.dsptk.get_samplerate()))

    def cmd_install_profile(self):
        if len(self.args.parameters) > 0:
            filename = self.args.parameters[0]
        else:
            print("profile filename missing")
            sys.exit(1)

        xmlfile = None
        if (filename.startswith("http://") or
                filename.startswith("https://")):
            # Download and store a local copy
            try:
                xmlfile = urllib.request.urlopen(filename)
            except IOError as e:
                print("can't download {} ({})".format(filename, e))
                sys.exit(1)
        else:
            try:
                xmlfile = open(filename)
            except IOError as e:
                print("can't open {} ({})".format(filename, e))
                sys.exit(1)

        try:
            data = xmlfile.read()
        except IOError as e:
            print("can't read {} ({})".format(filename, e))
            sys.exit(1)

        res = self.dsptk.install_profile_from_content(data)

        if res:
            print("DSP profile {} installed".format(filename))
        else:
            print("Failed to install DSP profile {}".format(filename))

    def cmd_write_reg(self):
        if len(self.args.parameters) > 1:
            reg = parse_int(self.args.parameters[0])
            value = parse_int(self.args.parameters[1])
        else:
            print("parameter missing, need addr value")

        data = [(value >> 8) & 0xff, value & 0xff]
        self.dsptk.sigmatcp.write_memory(reg, data)
        sys.exit(1)

    def cmd_write_mem(self):
        if len(self.args.parameters) > 1:
            reg = parse_int(self.args.parameters[0])
            value = parse_int(self.args.parameters[1])
        else:
            print("parameter missing, need addr value")

        data = [(value >> 24) & 0xff,
                (value >> 16) & 0xff,
                (value >> 8) & 0xff,
                value & 0xff]
        self.dsptk.sigmatcp.write_memory(reg, data)
        sys.exit(1)

    def cmd_check_eeprom(self):
        checksum1 = self.dsptk.sigmatcp.program_checksum()
        self.dsptk.reset()
        time.sleep(2)
        checksum2 = self.dsptk.sigmatcp.program_checksum()
        cs1 = ''.join(["%02X" % x for x in checksum1])
        cs2 = ''.join(["%02X" % x for x in checksum2])

        if checksum1 == checksum2:
            print("EEPROM content matches running profile, checksum {}".format(cs1))
        else:
            print("Checksums do not match {} != {}".format(cs1, cs2))

    def cmd_selfboot(self):
        val = 0
        if len(self.args.parameters) > 0:
            val = parse_int(self.args.parameters[0])
            rw = GPIO_WRITE
        else:
            rw = GPIO_READ

        logging.error("dsptk selfboot %s %s", val, rw)

        res = self.dsptk.sigmatcp.readwrite_gpio(rw, GPIO_SELFBOOT, val)
        print(res)

    def cmd_servers(self):
        if zeroconf_enabled:
            zeroconf = Zeroconf()
            listener = ZeroConfListener()
            ServiceBrowser(zeroconf, ZEROCONF_TYPE, listener)
            print("Looking for devices")
            time.sleep(5)
            zeroconf.close()
            for name, info in listener.devices.items():
                print("{}: {}".format(name, info))
        else:
            print("Zeroconf library not available")

    def cmd_store_settings(self):

        settingsfile = self.args.parameters[0]
        try:
            xmlfile = self.args.parameters[1]
        except:
            xmlfile = None

        (registerfile, xmlprofile) = self.read_register_and_xml(
            settingsfile, xmlfile)

        registerfile.update_xml_profile(xmlprofile)

        self.write_back_xml(xmlprofile, xmlfile)

    def cmd_apply_settings(self):

        settingsfile = self.args.parameters[0]
        try:
            xmlfile = self.args.parameters[1]
        except:
            xmlfile = None

        (registerfile, xmlprofile) = self.read_register_and_xml(
            settingsfile, xmlfile)

        changes = registerfile.get_updates(xmlprofile)
        self.dsptk.hibernate(True)
        for addr in changes:
            logging.debug("writing {} to {}", changes[addr], addr)
            self.dsptk.sigmatcp.write_memory(addr, changes[addr])
        self.dsptk.hibernate(False)

    def cmd_store_filters(self):
        attributes = [ATTRIBUTE_IIR_FILTER_LEFT,
                      ATTRIBUTE_IIR_FILTER_RIGHT,
                      ATTRIBUTE_FIR_FILTER_LEFT,
                      ATTRIBUTE_FIR_FILTER_RIGHT]
        self.store_attributes(attributes)
        print("Stored filter settings")

    def cmd_store(self):
        self.store_attributes(REGISTER_ATTRIBUTES)
        print("Stored filter settings")

    def cmd_get_memory(self):
        print("Not yet implemented")
        sys.exit(1)

    def read_register_and_xml(self, settingsfile, xmlfile):
        if xmlfile is not None:
            try:
                with open(xmlfile) as infile:
                    xml = infile.read()
            except IOError:
                print("can't read {}".format(xmlfile))
                sys.exit(1)
        else:
            xml = self.dsptk.generic_request(COMMAND_XML,
                                             COMMAND_XML_RESPONSE).decode()
            if xml is None or len(xml) == 0:
                print("server did not provide XML file")
                sys.exit(1)

        xmlprofile = XmlProfile()
        try:
            xmlprofile.read_from_text(xml)
        except:
            print("can't parse XML profile")
            sys.exit(1)

        try:
            registerfile = SettingsFile(settingsfile, xmlprofile.samplerate())
        except:
            print("can't parse settings file")
            sys.exit(1)

        return(registerfile, xmlprofile)

    def write_back_xml(self, xmlprofile, xmlfile=None):
        if xmlfile is None:
            print("writing back updated DSP profile")
            res = self.dsptk.install_profile_from_content(str(xmlprofile))
            if res:
                print("DSP profile updated on server")
            else:
                print("Failed to update DSP profile")
                sys.exit(1)
        else:
            backupfile = xmlfile + ".bak"
            try:
                os.rename(xmlfile, backupfile)
            except:
                print("can't write rename %s to %s", xmlfile, backupfile)
                sys.exit(1)

            try:
                with open(xmlfile, "w") as outfile:
                    outfile.write(str(xmlprofile))
            except:
                print("can't write %s", xmlfile)
                sys.exit(1)

            print("Updated {}, backup copy {}".format(xmlfile,
                                                      backupfile))

    def store_attributes(self, attributes):
        '''
        Store specific attributes from RAM into DSP EEPROM
        '''
        xml = self.dsptk.generic_request(COMMAND_XML,
                                         COMMAND_XML_RESPONSE)
        if len(xml) == 0:
            print("can't retrieve XML file from server")
            sys.exit(1)

        xmlprofile = XmlProfile()
        xmlprofile.read_from_text(xml.decode("utf-8", errors="replace"))

        replace = {}

        for attribute in attributes:
            (addr, length) = xmlprofile.get_addr_length(attribute)
            if addr is None:
                continue

            while length > 0:
                data = self.dsptk.sigmatcp.read_data(addr,
                                                     self.dsptk.dsp.WORD_LENGTH)
                replace[addr] = data
                addr += 1
                length -= 1

        xmlprofile.replace_eeprom_cells(replace)
        xmlprofile.replace_ram_cells(replace)
        self.write_back_xml(xmlprofile)

    def main(self):

        parser = argparse.ArgumentParser(description='HiFiBerry DSP toolkit')
        parser.add_argument('--delay',
                            help='delay for loop operations in ms',
                            type=int,
                            required=False,
                            default=1000)
        parser.add_argument('--host',
                            help='hostname or IP address of the server to connect to',
                            required=False,
                            default="127.0.0.1")
        parser.add_argument('command',
                            choices=sorted(self.command_map.keys()))
        parser.add_argument('parameters', nargs='*')

        self.args = parser.parse_args()

        self.dsptk.set_ip(self.args.host)

        # Run the command
        self.command_map[self.args.command]()


if __name__ == "__main__":
    cmdline = CommandLine()
    cmdline.main()


class ZeroConfListener:

    def __init__(self):
        self.devices = {}

    def remove_service(self, _zeroconf, _type, _name):
        pass

    def add_service(self, zeroconf, service_type, name):
        if service_type == ZEROCONF_TYPE:
            info = zeroconf.get_service_info(service_type, name)
            ip = socket.inet_ntoa(info.address)
            try:
                version = info.properties[b'version'].decode()
            except:
                version = "unknown"
            hostinfo = "{}:{} (version {})".format(ip,
                                                   info.port,
                                                   version)
            self.devices[name] = hostinfo
