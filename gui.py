#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NRAU-Baltic Log Cross-Checker GUI

A graphical interface for cross-checking NRAU-Baltic ham radio contest logs.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from check import (
    read_counties,
    read_logs,
    find_qso,
    match_time,
    match_time_window,
    cic,
    MAX_MINUTE_DELTA,
)


@dataclass
class QSOValidation:
    """Holds validation result for a single QSO."""
    qso: object  # QSO object from cabrillo
    points: int  # 0, 1, or 2
    error_message: str  # Empty if valid
    multiplier: str  # County code if earned, else empty


@dataclass
class ParticipantResult:
    """Holds all validation results for a participant."""
    callsign: str
    mode: str
    power: str
    county: str
    checklog: str
    qso_validations: List[QSOValidation] = field(default_factory=list)

    @property
    def qso_count_80m(self) -> int:
        return sum(1 for v in self.qso_validations
                   if v.points > 0 and v.qso.freq[0] == "3")

    @property
    def qso_count_40m(self) -> int:
        return sum(1 for v in self.qso_validations
                   if v.points > 0 and v.qso.freq[0] == "7")

    @property
    def points_80m(self) -> int:
        return sum(v.points for v in self.qso_validations
                   if v.points > 0 and v.qso.freq[0] == "3")

    @property
    def points_40m(self) -> int:
        return sum(v.points for v in self.qso_validations
                   if v.points > 0 and v.qso.freq[0] == "7")

    @property
    def mults_80m(self) -> List[str]:
        seen = []
        for v in self.qso_validations:
            if v.multiplier and v.qso.freq[0] == "3" and v.multiplier not in seen:
                seen.append(v.multiplier)
        return seen

    @property
    def mults_40m(self) -> List[str]:
        seen = []
        for v in self.qso_validations:
            if v.multiplier and v.qso.freq[0] == "7" and v.multiplier not in seen:
                seen.append(v.multiplier)
        return seen

    @property
    def total_score(self) -> int:
        return (self.points_80m + self.points_40m) * (len(self.mults_80m) + len(self.mults_40m))

    @property
    def total_qsos(self) -> int:
        return len(self.qso_validations)

    @property
    def valid_qsos(self) -> int:
        return sum(1 for v in self.qso_validations if v.points == 2)

    @property
    def partial_qsos(self) -> int:
        return sum(1 for v in self.qso_validations if v.points == 1)

    @property
    def invalid_qsos(self) -> int:
        return sum(1 for v in self.qso_validations if v.points == 0)


def validate_exchange(my_qso, other_qso, counties: dict) -> tuple:
    """
    Validate exchange between two QSOs.
    Returns (points, error_message).
    """
    my_tx_exch = my_qso.de_exch
    other_rx_exch = other_qso.dx_exch
    my_rx_exch = my_qso.dx_exch
    other_tx_exch = other_qso.de_exch

    if len(my_tx_exch) != 3:
        return 0, f"Incomplete TX message: {my_tx_exch}"

    if len(my_rx_exch) != 3:
        return 0, f"Incomplete RX message: {my_rx_exch}"

    if my_rx_exch[0] != other_tx_exch[0]:
        return 1, f"RX RST mismatch: you copied {other_tx_exch[0]} as {my_rx_exch[0]}"

    try:
        if int(my_rx_exch[1]) != int(other_tx_exch[1]):
            return 1, f"RX number mismatch: you copied {other_tx_exch[1]} as {my_rx_exch[1]}"
    except ValueError:
        return 1, f"Invalid QSO number format: {my_rx_exch[1]} or {other_tx_exch[1]}"

    if my_rx_exch[2] != other_tx_exch[2]:
        return 1, f"RX county mismatch: you copied {other_tx_exch[2]} as {my_rx_exch[2]}"

    return 2, ""


def validate_qso_gui(contest: dict, my_qso, other_callsign: str,
                     counties: dict, shadow_stations: dict, run: int = 1) -> tuple:
    """
    Validate a single QSO. Returns (points, error_message, matched_qso).
    Adapted from match_nrau() in check.py.
    """
    my_freq = int(my_qso.freq)

    # Check if other station submitted a log
    if other_callsign not in contest:
        if other_callsign in shadow_stations and shadow_stations[other_callsign].get(my_qso.mo + "_count", 0) >= 10:
            try:
                country = cic.get_country_name(my_qso.dx_call)
                if country in counties and my_qso.dx_exch[2] not in counties[country]:
                    return 0, f"No county {my_qso.dx_exch[2]} in {country}", None
                return 1, f"Found 10+ QSOs of station {other_callsign} (no log)", None
            except Exception:
                return 0, f"Log not received from {other_callsign}", None
        return 0, f"Log not received from {other_callsign}", None

    other_qso = find_qso(contest, other_callsign, my_qso.de_call, my_qso.freq[0], run)

    if not other_qso:
        return 0, f"QSO not found in {other_callsign}'s log", None

    # Validate CW frequency bands
    if my_qso.mo == "CW" and not (
        (my_freq >= 3510 and my_freq <= 3560) or
        my_freq == 3500 or
        (my_freq >= 7010 and my_freq <= 7060) or
        my_freq == 7000
    ):
        return 0, f"CW QSO frequency {my_freq} out of contest band", None

    # Validate PH frequency bands
    if my_qso.mo == "PH" and not (
        (my_freq >= 3600 and my_freq <= 3650) or
        (my_freq >= 3700 and my_freq <= 3775) or
        my_freq == 3500 or
        (my_freq >= 7050 and my_freq <= 7100) or
        (my_freq >= 7130 and my_freq <= 7200) or
        my_freq == 7000
    ):
        return 0, f"PH QSO frequency {my_freq} out of contest band", None

    # Validate time window
    if not match_time_window(my_qso.date):
        return 0, f"QSO logged outside contest time ({my_qso.date})", None

    # Validate time match
    if not match_time(my_qso.date, other_qso.date):
        next_qso = find_qso(contest, other_callsign, my_qso.de_call, my_qso.freq[0], run + 1)
        if next_qso:
            return validate_qso_gui(contest, my_qso, other_callsign, counties, shadow_stations, run + 1)
        return 0, f"Time differs: {my_qso.date}, {other_qso.date}", None

    # Validate exchange
    points, error = validate_exchange(my_qso, other_qso, counties)
    return points, error, other_qso


def build_shadow_stations(contest: dict) -> dict:
    """Build dictionary of stations that were worked but didn't submit logs."""
    shadow = {}
    for call, qsos in contest.items():
        for qso in qsos:
            if qso.dx_call not in contest:
                if qso.dx_call not in shadow:
                    shadow[qso.dx_call] = {}
                if qso.mo + "_count" not in shadow[qso.dx_call]:
                    shadow[qso.dx_call][qso.mo + "_count"] = 0
                if qso.mo not in shadow[qso.dx_call]:
                    shadow[qso.dx_call][qso.mo] = []
                shadow[qso.dx_call][qso.mo].append(qso.de_call)
                shadow[qso.dx_call][qso.mo + "_count"] += 1
    return shadow


def validate_all(contest: dict, metadata: dict, counties: dict) -> Dict[str, ParticipantResult]:
    """Validate all QSOs in the contest and return results."""
    shadow_stations = build_shadow_stations(contest)
    results = {}

    for call, qsos in contest.items():
        if not qsos:
            continue

        result = ParticipantResult(
            callsign=call,
            mode=qsos[0].mo,
            power=metadata.get(call, {}).get("power", "HIGH"),
            county=qsos[0].de_exch[2] if len(qsos[0].de_exch) >= 3 else "??",
            checklog=metadata.get(call, {}).get("checklog", "N"),
        )

        earned_mults_80m = []
        earned_mults_40m = []

        for qso in qsos:
            points, error, matched_qso = validate_qso_gui(
                contest, qso, qso.dx_call, counties, shadow_stations
            )

            multiplier = ""
            if points > 0:
                county = qso.dx_exch[2] if len(qso.dx_exch) >= 3 else ""
                mult_ok = True

                if points == 1:
                    try:
                        country = cic.get_country_name(qso.dx_call)
                        if country in counties and county not in counties[country]:
                            mult_ok = False
                    except Exception:
                        mult_ok = False

                    if matched_qso and matched_qso.de_exch[2] != qso.dx_exch[2]:
                        mult_ok = False

                if mult_ok and county:
                    if qso.freq[0] == "7" and county not in earned_mults_40m:
                        earned_mults_40m.append(county)
                        multiplier = county
                    elif qso.freq[0] == "3" and county not in earned_mults_80m:
                        earned_mults_80m.append(county)
                        multiplier = county

            result.qso_validations.append(QSOValidation(
                qso=qso,
                points=points,
                error_message=error,
                multiplier=multiplier,
            ))

        results[call] = result

    return results


class NRAUCheckerGUI:
    """Main GUI application class."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("NRAU-Baltic Log Cross-Checker")
        self.root.geometry("1200x700")

        # Data storage
        self.counties = {}
        self.cw_contest = {}
        self.cw_metadata = {}
        self.ph_contest = {}
        self.ph_metadata = {}
        self.cw_results = {}
        self.ph_results = {}
        self.selected_mode = None  # Currently selected file's mode
        self.selected_call = None  # Currently selected file's callsign

        # Load counties
        try:
            self.counties = read_counties()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load counties.json: {e}")

        self._create_menu()
        self._create_widgets()
        self._update_status("Ready. Use File menu to load logs.")

    def _create_menu(self):
        """Create the menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load CW Logs...", command=self._load_cw_logs)
        file_menu.add_command(label="Load PH Logs...", command=self._load_ph_logs)
        file_menu.add_separator()
        file_menu.add_command(label="Run Validation", command=self._run_validation)
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV...", command=self._export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

    def _create_widgets(self):
        """Create the main GUI widgets."""
        # Main paned window
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left pane
        left_frame = ttk.Frame(self.paned, width=350)
        self.paned.add(left_frame, weight=1)

        # Log files list with columns
        files_frame = ttk.LabelFrame(left_frame, text="Log Files")
        files_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.files_tree = ttk.Treeview(files_frame, columns=("call", "mode", "status"),
                                       show="headings", selectmode="browse")
        self.files_tree.heading("call", text="Call")
        self.files_tree.heading("mode", text="Mode")
        self.files_tree.heading("status", text="Status")
        self.files_tree.column("call", width=100)
        self.files_tree.column("mode", width=50)
        self.files_tree.column("status", width=80)

        files_scrollbar = ttk.Scrollbar(files_frame, orient=tk.VERTICAL,
                                        command=self.files_tree.yview)
        self.files_tree.config(yscrollcommand=files_scrollbar.set)
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.files_tree.bind("<<TreeviewSelect>>", self._on_file_select)

        # QSO list
        qso_frame = ttk.LabelFrame(left_frame, text="QSOs")
        qso_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.qso_tree = ttk.Treeview(qso_frame, columns=("time", "dx", "band", "pts"),
                                     show="headings", selectmode="browse")
        self.qso_tree.heading("time", text="Time")
        self.qso_tree.heading("dx", text="DX Call")
        self.qso_tree.heading("band", text="Band")
        self.qso_tree.heading("pts", text="Pts")
        self.qso_tree.column("time", width=80)
        self.qso_tree.column("dx", width=100)
        self.qso_tree.column("band", width=50)
        self.qso_tree.column("pts", width=40)

        qso_scrollbar = ttk.Scrollbar(qso_frame, orient=tk.VERTICAL,
                                      command=self.qso_tree.yview)
        self.qso_tree.config(yscrollcommand=qso_scrollbar.set)
        self.qso_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        qso_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.qso_tree.bind("<<TreeviewSelect>>", self._on_qso_select)

        # Configure tags for color coding
        self.qso_tree.tag_configure("valid", background="#90EE90")  # Light green
        self.qso_tree.tag_configure("partial", background="#FFD700")  # Gold/Yellow
        self.qso_tree.tag_configure("invalid", background="#FF6B6B")  # Light red

        # Legend
        legend_frame = ttk.Frame(left_frame)
        legend_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(legend_frame, text="Legend:", font=("", 9, "bold")).pack(side=tk.LEFT)

        valid_label = tk.Label(legend_frame, text=" Valid (2pts) ", bg="#90EE90")
        valid_label.pack(side=tk.LEFT, padx=2)
        partial_label = tk.Label(legend_frame, text=" Partial (1pt) ", bg="#FFD700")
        partial_label.pack(side=tk.LEFT, padx=2)
        invalid_label = tk.Label(legend_frame, text=" Invalid (0pts) ", bg="#FF6B6B")
        invalid_label.pack(side=tk.LEFT, padx=2)

        # Right pane
        right_frame = ttk.Frame(self.paned)
        self.paned.add(right_frame, weight=2)

        # Participant summary
        summary_frame = ttk.LabelFrame(right_frame, text="Participant Summary")
        summary_frame.pack(fill=tk.X, padx=5, pady=5)

        self.summary_text = tk.Text(summary_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.summary_text.pack(fill=tk.X, padx=5, pady=5)

        # QSO validation details
        details_frame = ttk.LabelFrame(right_frame, text="QSO Validation Details")
        details_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.details_text = tk.Text(details_frame, wrap=tk.WORD, state=tk.DISABLED)
        details_scrollbar = ttk.Scrollbar(details_frame, orient=tk.VERTICAL,
                                          command=self.details_text.yview)
        self.details_text.config(yscrollcommand=details_scrollbar.set)
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        details_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure text tags
        self.details_text.tag_configure("header", font=("", 11, "bold"))
        self.details_text.tag_configure("valid", foreground="green", font=("", 10, "bold"))
        self.details_text.tag_configure("partial", foreground="orange", font=("", 10, "bold"))
        self.details_text.tag_configure("invalid", foreground="red", font=("", 10, "bold"))
        self.details_text.tag_configure("error", foreground="red")

        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var,
                                    relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _update_status(self, message: str):
        """Update the status bar message."""
        self.status_var.set(message)
        self.root.update_idletasks()

    def _load_cw_logs(self):
        """Load CW contest logs."""
        folder = filedialog.askdirectory(title="Select CW Logs Folder", initialdir="./CW")
        if folder:
            self._load_logs(folder, "CW")

    def _load_ph_logs(self):
        """Load PH contest logs."""
        folder = filedialog.askdirectory(title="Select PH Logs Folder", initialdir="./PH")
        if folder:
            self._load_logs(folder, "PH")

    def _load_logs(self, folder: str, mode: str):
        """Load logs from a folder."""
        if not folder.endswith("/"):
            folder += "/"

        try:
            self._update_status(f"Loading {mode} logs from {folder}...")
            contest, metadata = read_logs(folder)

            if mode == "CW":
                self.cw_contest = contest
                self.cw_metadata = metadata
            else:
                self.ph_contest = contest
                self.ph_metadata = metadata

            total_qsos = sum(len(qsos) for qsos in contest.values())
            self._update_status(f"Loaded {len(contest)} {mode} logs ({total_qsos} QSOs). "
                              f"CW: {len(self.cw_contest)} logs, PH: {len(self.ph_contest)} logs")

            # Update the files display immediately
            self._refresh_files_list()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load logs: {e}")
            self._update_status(f"Error loading logs: {e}")

    def _run_validation(self):
        """Run cross-check validation on loaded logs."""
        if not self.cw_contest and not self.ph_contest:
            messagebox.showwarning("Warning", "No logs loaded. Please load CW or PH logs first.")
            return

        try:
            self._update_status("Running validation...")

            if self.cw_contest:
                self._update_status("Validating CW logs...")
                self.cw_results = validate_all(self.cw_contest, self.cw_metadata, self.counties)

            if self.ph_contest:
                self._update_status("Validating PH logs...")
                self.ph_results = validate_all(self.ph_contest, self.ph_metadata, self.counties)

            # Update display with validation status
            self._refresh_files_list()

            # Calculate statistics
            total_qsos = sum(r.total_qsos for r in self.cw_results.values()) + \
                        sum(r.total_qsos for r in self.ph_results.values())
            total_errors = sum(r.invalid_qsos + r.partial_qsos for r in self.cw_results.values()) + \
                          sum(r.invalid_qsos + r.partial_qsos for r in self.ph_results.values())

            self._update_status(f"Validation complete. {len(self.cw_results)} CW logs, "
                              f"{len(self.ph_results)} PH logs, {total_qsos} QSOs, {total_errors} issues")

        except Exception as e:
            messagebox.showerror("Error", f"Validation failed: {e}")
            self._update_status(f"Validation error: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_files_list(self):
        """Refresh the files list showing all loaded logs."""
        # Clear existing items
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)

        # Add CW logs
        for call in sorted(self.cw_contest.keys()):
            if call in self.cw_results:
                r = self.cw_results[call]
                status = f"{r.valid_qsos}/{r.total_qsos} OK"
            else:
                qso_count = len(self.cw_contest[call])
                status = f"{qso_count} QSOs"
            self.files_tree.insert("", tk.END, iid=f"CW_{call}",
                                  values=(call, "CW", status))

        # Add PH logs
        for call in sorted(self.ph_contest.keys()):
            if call in self.ph_results:
                r = self.ph_results[call]
                status = f"{r.valid_qsos}/{r.total_qsos} OK"
            else:
                qso_count = len(self.ph_contest[call])
                status = f"{qso_count} QSOs"
            self.files_tree.insert("", tk.END, iid=f"PH_{call}",
                                  values=(call, "PH", status))

        # Clear QSO list and details
        for item in self.qso_tree.get_children():
            self.qso_tree.delete(item)

        self._clear_summary()
        self._clear_details()

    def _on_file_select(self, event):
        """Handle file/participant selection."""
        selection = self.files_tree.selection()
        if not selection:
            return

        # Parse the item ID (format: "MODE_CALLSIGN")
        item_id = selection[0]
        if "_" not in item_id:
            return

        mode, callsign = item_id.split("_", 1)
        self.selected_mode = mode
        self.selected_call = callsign

        # Get the results or contest data
        if mode == "CW":
            results = self.cw_results
            contest = self.cw_contest
            metadata = self.cw_metadata
        else:
            results = self.ph_results
            contest = self.ph_contest
            metadata = self.ph_metadata

        # Clear QSO list
        for item in self.qso_tree.get_children():
            self.qso_tree.delete(item)

        if callsign in results:
            # Show validated results
            result = results[callsign]
            self._update_summary(result)

            for i, v in enumerate(result.qso_validations):
                time_str = v.qso.date.strftime("%H%M") if v.qso.date else "????"
                band = "80m" if v.qso.freq[0] == "3" else "40m"

                if v.points == 2:
                    tag = "valid"
                elif v.points == 1:
                    tag = "partial"
                else:
                    tag = "invalid"

                self.qso_tree.insert("", tk.END, iid=str(i),
                                   values=(time_str, v.qso.dx_call, band, v.points),
                                   tags=(tag,))
        elif callsign in contest:
            # Show unvalidated logs (before validation)
            qsos = contest[callsign]
            meta = metadata.get(callsign, {})

            # Show basic summary without validation
            self.summary_text.config(state=tk.NORMAL)
            self.summary_text.delete("1.0", tk.END)
            county = qsos[0].de_exch[2] if qsos and len(qsos[0].de_exch) >= 3 else "??"
            self.summary_text.insert("1.0", f"""Callsign: {callsign}
Mode: {mode}  |  Power: {meta.get('power', '?')}  |  County: {county}

QSOs: {len(qsos)} (not yet validated)

Run validation to see detailed results.""")
            self.summary_text.config(state=tk.DISABLED)

            # Show QSOs without validation status
            for i, qso in enumerate(qsos):
                time_str = qso.date.strftime("%H%M") if qso.date else "????"
                band = "80m" if qso.freq[0] == "3" else "40m"
                self.qso_tree.insert("", tk.END, iid=str(i),
                                   values=(time_str, qso.dx_call, band, "-"))

        self._clear_details()

    def _on_qso_select(self, event):
        """Handle QSO selection."""
        selection = self.qso_tree.selection()
        if not selection:
            return

        if not hasattr(self, 'selected_mode') or not hasattr(self, 'selected_call'):
            return

        mode = self.selected_mode
        callsign = self.selected_call

        if mode == "CW":
            results = self.cw_results
            contest = self.cw_contest
        else:
            results = self.ph_results
            contest = self.ph_contest

        if callsign not in results and callsign not in contest:
            return

        qso_idx = int(selection[0])

        if callsign in results:
            # Show validated QSO details
            result = results[callsign]
            if qso_idx >= len(result.qso_validations):
                return
            v = result.qso_validations[qso_idx]
            self._update_details(v)
        elif callsign in contest:
            # Show unvalidated QSO details
            qsos = contest[callsign]
            if qso_idx >= len(qsos):
                return
            qso = qsos[qso_idx]
            self._update_details_unvalidated(qso)

    def _update_summary(self, result: ParticipantResult):
        """Update the participant summary panel."""
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)

        text = f"""Callsign: {result.callsign}
Mode: {result.mode}  |  Power: {result.power}  |  County: {result.county}  |  Checklog: {result.checklog}

QSOs: {result.total_qsos}  (Valid: {result.valid_qsos}, Partial: {result.partial_qsos}, Invalid: {result.invalid_qsos})

80m: {result.qso_count_80m} QSOs, {result.points_80m} pts, {len(result.mults_80m)} mults
40m: {result.qso_count_40m} QSOs, {result.points_40m} pts, {len(result.mults_40m)} mults

Total Score: {result.total_score}"""

        self.summary_text.insert("1.0", text)
        self.summary_text.config(state=tk.DISABLED)

    def _clear_summary(self):
        """Clear the summary panel."""
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", "Select a participant from the list")
        self.summary_text.config(state=tk.DISABLED)

    def _update_details(self, v: QSOValidation):
        """Update the QSO details panel."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        qso = v.qso
        band = "80m (3.5 MHz)" if qso.freq[0] == "3" else "40m (7 MHz)"

        self.details_text.insert(tk.END, "QSO Information\n", "header")
        self.details_text.insert(tk.END, f"""
Time: {qso.date}
Frequency: {qso.freq} kHz ({band})
Mode: {qso.mo}

Your Call: {qso.de_call}
DX Call: {qso.dx_call}

Sent Exchange: {' '.join(qso.de_exch)}
Received Exchange: {' '.join(qso.dx_exch)}
""")

        self.details_text.insert(tk.END, "\nValidation Result\n", "header")

        if v.points == 2:
            self.details_text.insert(tk.END, "\nStatus: VALID (2 points)\n", "valid")
        elif v.points == 1:
            self.details_text.insert(tk.END, "\nStatus: PARTIAL (1 point)\n", "partial")
        else:
            self.details_text.insert(tk.END, "\nStatus: INVALID (0 points)\n", "invalid")

        if v.error_message:
            self.details_text.insert(tk.END, f"\nReason: {v.error_message}\n", "error")

        if v.multiplier:
            self.details_text.insert(tk.END, f"\nMultiplier earned: +{v.multiplier}")

        self.details_text.config(state=tk.DISABLED)

    def _update_details_unvalidated(self, qso):
        """Update the QSO details panel for unvalidated QSO."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        band = "80m (3.5 MHz)" if qso.freq[0] == "3" else "40m (7 MHz)"

        self.details_text.insert(tk.END, "QSO Information\n", "header")
        self.details_text.insert(tk.END, f"""
Time: {qso.date}
Frequency: {qso.freq} kHz ({band})
Mode: {qso.mo}

Your Call: {qso.de_call}
DX Call: {qso.dx_call}

Sent Exchange: {' '.join(qso.de_exch)}
Received Exchange: {' '.join(qso.dx_exch)}
""")

        self.details_text.insert(tk.END, "\nValidation Result\n", "header")
        self.details_text.insert(tk.END, "\nNot yet validated. Run validation to see results.")

        self.details_text.config(state=tk.DISABLED)

    def _clear_details(self):
        """Clear the details panel."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", "Select a QSO to view details")
        self.details_text.config(state=tk.DISABLED)

    def _export_csv(self):
        """Export results to CSV file."""
        if not self.cw_results and not self.ph_results:
            messagebox.showwarning("Warning", "No validation results. Run validation first.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Results as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return

        try:
            with open(filepath, "w") as f:
                f.write("MODE,CALL,QSO_COUNT_80m,QSO_COUNT_40m,POINT_80m,POINT_40m,"
                       "MULT_80m,MULT_40m,SCORE,POWER,COUNTY,CHECKLOG\n")

                for results in [self.cw_results, self.ph_results]:
                    for call, r in sorted(results.items()):
                        f.write(f"{r.mode},{r.callsign},{r.qso_count_80m},{r.qso_count_40m},"
                               f"{r.points_80m},{r.points_40m},{len(r.mults_80m)},{len(r.mults_40m)},"
                               f"{r.total_score},{r.power},{r.county},{r.checklog}\n")

            self._update_status(f"Results exported to {filepath}")
            messagebox.showinfo("Export Complete", f"Results exported to:\n{filepath}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")


def main():
    root = tk.Tk()
    app = NRAUCheckerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
