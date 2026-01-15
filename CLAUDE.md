# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a cross-checking tool for the NRAU-Baltic ham radio contest. It validates Cabrillo log files submitted by participants, checking for rule violations and generating results/error reports.

## Commands

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Log Cross-Checker
```bash
python check.py > results.csv
```
Outputs CSV results to stdout, statistics to stderr. Generates `.ubn` error report files alongside each log.

### Generate Award Diplomas (in awards/ directory)
```bash
cd awards
pip install -r requirements.txt
python awards.py
```
Requires `nrau_2022_awards.csv` input file and `nrau-template-2022.pdf` template.

## Architecture

### Main Cross-Checker (check.py)

Single-file Python script that:
1. Reads Cabrillo log files from `CW/` and `PH/` directories (`.txt` extension)
2. Cross-references QSOs between participants to validate contacts
3. Checks QSOs against contest rules (frequency bands, time windows, exchange format)
4. Generates per-participant `.ubn` error report files
5. Outputs CSV with final scores

**Key validation logic:**
- `match_nrau()`: Main QSO validation - checks if contact exists in other station's log, validates frequency band, time window
- `match_exch()`: Validates RST, serial number, and county exchange match between stations
- `match_time()`: Verifies QSO times match within 5-minute window
- `match_time_window()`: Checks QSO falls within contest period

**Scoring:** 2 points for perfect match, 1 point for partial match (RST/number/county error), 0 points for invalid QSO

**Shadow stations:** Stations not submitting logs but worked by 10+ participants get partial credit

### Data Files

- `counties.json`: Maps 2-letter county codes to names for Nordic/Baltic countries (Estonia, Latvia, Lithuania, Finland, Sweden, Norway, Denmark, Iceland)
- `CW/` and `PH/`: Contain submitted Cabrillo log files (`.txt`) and generated error reports (`.ubn`)

### Awards Generator (awards/awards.py)

Generates PDF award certificates by overlaying callsign and achievements onto a template PDF.

## Contest-Specific Constants

Contest times and frequency ranges are hardcoded in `check.py`:
- PH contest: starts 06:30 UTC, 2 hours
- CW contest: starts 09:00 UTC, 2 hours
- CW bands: 3510-3560 kHz, 7010-7060 kHz
- PH bands: 3600-3650/3700-3775 kHz, 7050-7100/7130-7200 kHz

Date/year must be updated in `PH_CONTEST_START` and `CW_CONTEST_START` variables for each year's contest.
