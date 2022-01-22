#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : Simonas Kareiva LY2EN <ly2en@qrz.lt>
# Created Date: 2022-01-20
# version ='0.1'
# ---------------------------------------------------------------------------
""" This script cross-checks the NRAU-Baltic logs in CW and PH categories 
    Usage: python check.py > results.csv

    Logs should be placed in folders "CW" and "PH" respectively
"""
# ---------------------------------------------------------------------------

import os
import sys
import json
from datetime import date
from pyhamtools import LookupLib, Callinfo
from cabrillo.parser import QSO, parse_log_file

cw = {}
ph = {}
nqso = 0
nfiles = 0
mistakes = 0
logext = ".txt"
max_time_delta = 3
shadow_stations = {}

my_lookuplib = LookupLib(lookuptype="countryfile")
cic = Callinfo(my_lookuplib)


def read_counties():
    c = open("counties.json")
    data = json.load(c)
    c.close()
    return data


def read_logs(folder):
    global nfiles, nqso
    _ret = {}
    _meta = {}
    files = os.listdir(folder)
    for file in files:
        if file.endswith(logext):
            cab = parse_log_file(folder + file, ignore_unknown_key=True)
            _ret[cab.callsign] = cab.qso
            checklog = "N"
            power = "HIGH"

            if hasattr(cab, "category_power") and cab.category_power is not None:
                power = cab.category_power

            if hasattr(cab, "category"):
                if cab.category.__contains__("HIGH") or cab.category.__contains__("HP"):
                    power = "HIGH"
                if cab.category.__contains__("LOW") or cab.category.__contains__("LP"):
                    power = "LOW"
                if cab.category.__contains__("CHECKLOG"):
                    checklog = "Y"

            if hasattr(cab, "category"):
                if cab.category.__contains__("MULTI"):
                    power = "MULTI"

            if hasattr(cab, "category_operator"):
                if cab.category_operator == "MULTI-OP":
                    power = "MULTI"
                if cab.category_operator == "CHECKLOG":
                    checklog = "Y"

            _meta[cab.callsign] = dict(power=power, checklog=checklog)

            if len(cab.qso) == 0:
                print("No QSO found")
            else:
                nqso += len(cab.qso)
                nfiles += 1
    return _ret, _meta


def find_qso(contest, call, dx, band, occurence=1):
    try:
        found = 0
        log = contest[call]
        for q in log:
            if q.dx_call == dx and q.freq[0] == band:
                found += 1
                if found == occurence:
                    return q
    except KeyError:
        return False


def match_exch(my_qso, other_qso, log):
    global counties
    # my tx, other rx
    my_tx_exch = my_qso.de_exch
    other_rx_exch = other_qso.dx_exch
    # my rx, other tx
    my_rx_exch = my_qso.dx_exch
    other_tx_exch = other_qso.de_exch
    # match RST:
    if len(my_tx_exch) != 3:
        log.write("0\t(Incomplete TX message: {:s})".format(str(my_exch)))
        return 0
    if len(other_rx_exch) != 3:
        log.write("0\t(Incomplete RX message: {:s})".format(str(my_exch)))
        return 0
    if my_tx_exch[0] != other_rx_exch[0]:
        log.write(
            "1\t(TX RST mismatch: sent as {:s}, received as {:s})".format(
                my_tx_exch[0], other_rx_exch[0]
            )
        )
        return 1
    if my_rx_exch[0] != other_tx_exch[0]:
        log.write(
            "1\t(RX RST mismatch: sent as {:s}, received as {:s})".format(
                other_tx_exch[0], my_rx_exch[0]
            )
        )
        return 1
    # match number:
    if int(my_rx_exch[1]) != int(other_tx_exch[1]):
        log.write(
            "1\t(Numbering mismatch: {:s} copied as {:s})".format(
                my_rx_exch[1], other_tx_exch[1]
            )
        )
        return 1

    # match county:
    if my_rx_exch[2] != other_tx_exch[2]:
        log.write(
            "1\t(County mismatch: {:s} copied as {:s})".format(
                other_tx_exch[2], my_rx_exch[2]
            )
        )
        return 1
    return 2


def match_time(date1, date2):
    global max_time_delta
    delta = date1 - date2
    if abs(delta.total_seconds()) > max_time_delta * 60:
        return False
    return True


def match_nrau(contest, my_qso, other_callsign, log, run=1):
    my_freq = int(my_qso.freq)
    if not other_callsign in contest:
        if shadow_stations[other_callsign][my_qso.mo + "_count"] >= 10:
            if my_qso.dx_exch[2] not in counties[cic.get_country_name(my_qso.dx_call)]:
                log.write(
                    "0\t(No county {:s} in {:s})".format(
                        my_qso.dx_exch[2], cic.get_country_name(my_qso.dx_call)
                    )
                )
                return 0
            log.write(
                "1\t(Found 10+ QSOs of station {:s})".format(my_qso.mo, other_callsign)
            )
            return 1
        else:
            log.write("0\t(Log not received from {:s})".format(other_callsign))
            return 0

    other_qso = find_qso(contest, other_callsign, my_qso.de_call, my_qso.freq[0], run)

    # TODO: check for similar time/exchange for errors in dx call
    # (this does not impact the result, just explains the case in UBN)
    if not other_qso:
        log.write(
            "0\t(QSO not found in {:s}'s log)".format(
                my_qso.mo,
                other_callsign,
            )
        )
        return 0

    if my_qso.mo == "CW" and not (
        (my_freq >= 3510 and my_freq <= 3560)
        or my_freq == 3500
        or (my_freq >= 7010 and my_freq <= 7060)
        or my_freq == 7000
    ):
        log.write("0\t(CW QSO frequency {:d} out of contest band)".format(my_freq))
        return 0

    if my_qso.mo == "PH" and not (
        (my_freq >= 3600 and my_freq <= 3650)
        or (my_freq >= 3700 and my_freq <= 3775)
        or my_freq == 3500
        or (my_freq >= 7050 and my_freq <= 7100)
        or (my_freq >= 7130 and my_freq <= 7200)
        or my_freq == 7000
    ):
        log.write("0\t(PH QSO frequency {:d} out of contest band)".format(my_freq))
        return 0

    if not match_time(my_qso.date, other_qso.date):
        # here check for possible dupes or repeated qsos
        next_qso = find_qso(
            contest, other_callsign, my_qso.de_call, my_qso.freq[0], run + 1
        )
        if next_qso:
            next_score = match_nrau(contest, my_qso, other_callsign, log, run + 1)
            if next_score > 0:
                return next_score
        else:
            log.write(
                "0\t(Time differs: {:s}, {:s})".format(str(my_qso.date), str(other_qso.date))
            )
            return 0

    # final exchange check:
    return match_exch(my_qso, other_qso, log)


def loop_all(filepath):
    global mistakes, shadow_stations
    results = {}
    contest, metadata = read_logs(filepath)
    for call, qsos in contest.items():
        # print("{:s}".format(call), end=", ", flush=True)
        results[call] = dict(
            call=call,
            mode=qsos[0].mo,
            qso_count_80m=0,
            qso_count_40m=0,
            points_80m=0,
            points_40m=0,
            mults_80m=[],
            mults_40m=[],
            score=0,
            power=metadata[call]["power"],
            county=qsos[0].de_exch[2],
            checklog=metadata[call]["checklog"],
        )

        log = open(filepath + call + ".log", "w+")
        for qso in qsos:
            if not qso.dx_call in contest:
                if not qso.dx_call in shadow_stations:
                    shadow_stations[qso.dx_call] = {}
                if not qso.mo + "_count" in shadow_stations[qso.dx_call]:
                    shadow_stations[qso.dx_call][qso.mo + "_count"] = 0
                if not qso.mo in shadow_stations[qso.dx_call]:
                    shadow_stations[qso.dx_call][qso.mo] = []
                shadow_stations[qso.dx_call][qso.mo].append(qso.de_call)
                shadow_stations[qso.dx_call][qso.mo + "_count"] += 1

        for qso in qsos:
            log.write(str(qso) + "\t")
            points = match_nrau(contest, qso, qso.dx_call, log)
            if points == 2:
                log.write("2")
            if points > 0:
                county = qso.dx_exch[2]
                mult_ok = True

                if points == 1:
                    country = cic.get_country_name(qso.dx_call)
                    # check if mult is ok in partial qso:
                    if county not in counties[country]:
                        mult_ok = False

                if qso.freq[0] == "7":
                    results[call]["qso_count_40m"] += 1
                    results[call]["points_40m"] += points
                    if mult_ok and county not in results[call]["mults_40m"]:
                        results[call]["mults_40m"].append(county)
                        log.write("\t+{:s}".format(county))
                if qso.freq[0] == "3":
                    results[call]["qso_count_80m"] += 1
                    results[call]["points_80m"] += points
                    if mult_ok and county not in results[call]["mults_80m"]:
                        results[call]["mults_80m"].append(county)
                        log.write("\t+{:s}".format(county))

            if points < 2:
                mistakes += 1
                qso.valid = False
            log.write("\n")
        log.close()
    return results


def print_csv_header():
    print(
        "MODE,"
        "CALL,"
        "QSO_COUNT_80m,"
        "QSO_COUNT_40m,"
        "POINT_80m,"
        "POINT_40m,"
        "MULT_80m,"
        "MULT_40m,"
        "SCORE,"
        "POWER,"
        "COUNTY,"
        "CHECKLOG"
    )


def results_to_csv(results):
    for item in results:
        participant = results[item]
        print(
            "{:s},{:s},{:d},{:d},{:d},{:d},{:d},{:d},{:d},{:s},{:s},{:s}".format(
                participant["mode"],
                participant["call"],
                participant["qso_count_80m"],
                participant["qso_count_40m"],
                participant["points_80m"],
                participant["points_40m"],
                len(participant["mults_80m"]),
                len(participant["mults_40m"]),
                (participant["points_80m"] + participant["points_40m"])
                * (len(participant["mults_80m"]) + len(participant["mults_40m"])),
                participant["power"],
                participant["county"],
                participant["checklog"],
            )
        )


cw_path = "./CW/"
ph_path = "./PH/"

counties = read_counties()

cw_results = loop_all(cw_path)
ph_results = loop_all(ph_path)


print_csv_header()
results_to_csv(cw_results)
results_to_csv(ph_results)

print(
    "{:d} QSO parsed ({:d} files), found {:d} mistakes".format(nqso, nfiles, mistakes),
    file=sys.stderr,
)
