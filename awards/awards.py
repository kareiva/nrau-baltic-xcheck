#!/usr/bin/env python

import io
import csv
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


awards_csv = csv.reader(open('nrau_2022_awards.csv'))
header = []
awards = {}
header = next(awards_csv)
rows = []
for row in awards_csv:
    if row[1] not in awards:
        awards[row[1]] = []
    awards[row[1]].append(row[6])

for call, achievements in awards.items():
    existing_pdf = PdfReader('nrau-template-2022.pdf')
    page = existing_pdf.pages[0];

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont('Helvetica', 48)
    can.drawString(240, 425, call)

    can.setFont('Helvetica', 15)
    start_y = 370
    step = 30
    for line in achievements:
        can.drawString(120, start_y, "● " + line)
        start_y = start_y - step

    can.save()

    packet.seek(0)
    new_pdf = PdfReader(packet)
    output = PdfWriter()

    page.mergePage(new_pdf.getPage(0))
    output.addPage(page)

    outputStream = open("./2022/" + call + ".pdf", "wb")
    output.write(outputStream)
    outputStream.close()