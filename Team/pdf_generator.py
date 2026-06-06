#!/usr/bin/env python3
"""
Smart Logistics PDF Generator
Genererer servicerapport og ansvarsfraskrivelse identisk med originale dokumenter.
"""

import re
import json
import base64
import sys
from io import BytesIO
from datetime import datetime

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ── PDF PARSER ────────────────────────────────────────────────────────────────

def parse_pdf_orders(pdf_path):
    """
    Parse en service-ordre PDF og returner liste af ordrer (én per kunde).
    Hver ordre svarer til 3 sider: 1/3 (kundeinfo), 2/3 (rapport), 3/3 (artikler).
    """
    orders = []
    
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        i = 0
        while i < len(pages):
            text = pages[i].extract_text() or ""
            
            # Find start af ny ordre (side 1/3)
            if "Service Report 1/3" in text or "1/3" in text:
                order = parse_order_pages(pages, i)
                if order:
                    orders.append(order)
                i += 3  # Spring 3 sider (1/3, 2/3, 3/3)
            else:
                i += 1
    
    return orders


def parse_order_pages(pages, start_idx):
    """Parse én ordre fra 3 sider."""
    if start_idx >= len(pages):
        return None
    
    # Side 1/3 — kundeinfo
    p1 = pages[start_idx].extract_text() or ""
    
    # Side 3/3 — artikler (hvis tilgængelig)
    p3 = ""
    if start_idx + 2 < len(pages):
        p3 = pages[start_idx + 2].extract_text() or ""
    
    def extract(label, text):
        """Udtræk feltværdi fra tekst."""
        # Fjern mellemrum i labels for matching
        clean = text.replace(" ", "")
        clean_label = label.replace(" ", "")
        pattern = re.compile(re.escape(clean_label) + r'(.+?)(?:\n|$)', re.IGNORECASE)
        m = pattern.search(clean)
        if m:
            val = m.group(1).strip()
            # Rekonstruér med mellemrum (simpel tilgang)
            return val
        return ""
    
    # Parse kundenavn med spaces
    name_match = re.search(r'Customer\s*name\s+(.+)', p1, re.IGNORECASE)
    customer_name = name_match.group(1).strip() if name_match else ""
    # Fix sammenkørte ord (pdfplumber fjerner interne spaces)
    customer_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', customer_name)
    
    addr1_match = re.search(r'Customer\s*address\s*1\s+(.+)', p1, re.IGNORECASE)
    address1 = addr1_match.group(1).strip() if addr1_match else ""
    # Fix adresser
    address1 = re.sub(r'(\d+)([A-Za-z,])', r'\1 \2', address1)
    address1 = re.sub(r'([a-z])([A-Z])', r'\1 \2', address1)
    
    postal_match = re.search(r'Postal\s*code/city/state\s+(.+)', p1, re.IGNORECASE)
    postal = postal_match.group(1).strip() if postal_match else ""
    # Fix postal code
    postal = re.sub(r'(\d{4})([A-Z])', r'\1 \2', postal)
    
    phone_match = re.search(r'Mobile\s*phone\s+(\+?\d+)', p1, re.IGNORECASE)
    mobile = phone_match.group(1).strip() if phone_match else ""
    
    email_match = re.search(r'Email\s+(\S+@\S+)', p1, re.IGNORECASE)
    email = email_match.group(1).strip() if email_match else ""
    
    order_match = re.search(r'Order\s*number\s+(\d+)', p1, re.IGNORECASE)
    order_number = order_match.group(1).strip() if order_match else ""
    
    delivery_match = re.search(r'Delivery\s*order\s*number\s+(\S+)', p1, re.IGNORECASE)
    delivery_number = delivery_match.group(1).strip() if delivery_match else ""
    
    store_match = re.search(r'Originating\s*store\s+(.+)', p1, re.IGNORECASE)
    store = store_match.group(1).strip() if store_match else ""
    store = re.sub(r'(\d+)([A-Z])', r'\1 ', store)
    
    provider_match = re.search(r'Service\s*provider\s+(.+)', p1, re.IGNORECASE)
    provider = provider_match.group(1).strip() if provider_match else "Bring E-Commerce & Logistics A/S"
    provider = re.sub(r'([a-z])([A-Z])', r'\1 \2', provider)
    provider = provider.replace("&", " & ").replace("  ", " ")
    
    product_match = re.search(r'Service\s*product\s+(\w+)', p1, re.IGNORECASE)
    product = product_match.group(1).strip() if product_match else "Assembly"
    
    # Bookede datoer
    date_matches = re.findall(r'(\d{2}-\d{2}-\d{4})\s+(\d{2}:\d{2})\s+(\d{2}-\d{2}-\d{4})\s+(\d{2}:\d{2})', p1)
    service_dates = []
    for m in date_matches:
        service_dates.append(f"{m[0]} {m[1]} — {m[2]} {m[3]}")
    
    # Parse artikler fra side 3/3
    articles = parse_articles(p3)
    
    return {
        "orderNumber": order_number,
        "deliveryOrderNumber": delivery_number,
        "customerName": customer_name,
        "customerAddress1": address1,
        "postalCityState": postal,
        "mobile": mobile,
        "email": email,
        "serviceProvider": provider if provider else "Bring E-Commerce & Logistics A/S",
        "serviceProduct": product,
        "originatingStore": store,
        "serviceDates": service_dates,
        "articles": articles,
        "printDate": datetime.now().strftime("%d-%m-%Y"),
    }


def parse_articles(text):
    """Parse artikeltabel fra side 3/3."""
    articles = []
    lines = text.split('\n')
    
    # Find linjer med artikeldata (har tal og item nr)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Match: beskrivelse + tal + item nr (8 cifre) + antal
        m = re.search(r'(.+?)\s+(\d+[,.]?\d*)\s+(\d+[,.]?\d*)\s+(\d+[,.]?\d*)\s+(\d{8})\s+(\d+)', line)
        if m:
            desc = m.group(1).strip()
            desc = re.sub(r'([a-z])([A-Z])', r'\1 \2', desc)
            articles.append({
                "description": desc,
                "netPrice": m.group(2),
                "vat": m.group(3),
                "grossPrice": m.group(4),
                "itemNo": m.group(5),
                "qty": m.group(6),
                "errorCode": ""
            })
    
    return articles


# ── SERVICE RAPPORT PDF ───────────────────────────────────────────────────────

def generate_service_report(order_data, report_data, output_path=None):
    """
    Genererer servicerapport PDF identisk med originaldokument.
    order_data: dict med kundeinfo fra parsed PDF
    report_data: dict med udfyldte felter fra team-appen
    output_path: sti til output fil (None = returner bytes)
    """
    buffer = BytesIO()
    target = output_path or buffer
    
    c = canvas.Canvas(target, pagesize=A4)
    w, h = A4
    
    # ── SIDE 1/3 — Kundeinfo ─────────────────────────────────────────────────
    draw_service_report_p1(c, w, h, order_data)
    c.showPage()
    
    # ── SIDE 2/3 — Udfyldt rapport ────────────────────────────────────────────
    draw_service_report_p2(c, w, h, order_data, report_data)
    c.showPage()
    
    # ── SIDE 3/3 — Artikler ───────────────────────────────────────────────────
    draw_service_report_p3(c, w, h, order_data)
    c.showPage()
    
    c.save()
    
    if output_path:
        return output_path
    else:
        buffer.seek(0)
        return buffer.read()


def setup_fonts(c):
    """Brug standard Helvetica fonts."""
    pass  # Bruger standard fonts


def draw_header(c, w, h, page_num, total=3):
    """Tegn header med 'Service Report X/3'."""
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 20*mm, "Service Report")
    c.setFont("Helvetica", 12)
    c.drawRightString(w - 20*mm, h - 20*mm, f"{page_num}/{total}")
    # Underline
    c.setLineWidth(0.5)
    c.line(20*mm, h - 23*mm, w - 20*mm, h - 23*mm)


def draw_field_row(c, x, y, label, value, label_w=70*mm, line_w=100*mm, font_size=9):
    """Tegn label + underline med værdi."""
    c.setFont("Helvetica", font_size)
    c.drawString(x, y, label)
    # Underline
    c.setLineWidth(0.4)
    c.line(x + label_w, y - 1, x + label_w + line_w, y - 1)
    # Værdi
    if value:
        c.setFont("Helvetica", font_size)
        c.drawString(x + label_w + 2, y, str(value))


def draw_checkbox(c, x, y, label, checked=False, size=4*mm):
    """Tegn checkbox med label."""
    c.setLineWidth(0.6)
    c.rect(x, y - size + 1*mm, size, size)
    if checked:
        c.line(x, y - size + 1*mm, x + size, y + 1*mm)
        c.line(x + size, y - size + 1*mm, x, y + 1*mm)
    c.setFont("Helvetica", 9)
    c.drawString(x + size + 2*mm, y, label)


def draw_service_report_p1(c, w, h, order):
    """Side 1/3 — Kundeoplysninger."""
    draw_header(c, w, h, 1)
    
    x = 20*mm
    y = h - 32*mm
    lh = 7*mm  # Linjehøjde
    label_w = 52*mm
    line_w = 110*mm
    
    fields = [
        ("Print date", order.get("printDate", "")),
        ("Customer name", order.get("customerName", "")),
        ("Customer address 1", order.get("customerAddress1", "")),
        ("Customer address 2", order.get("customerAddress2", "")),
        ("Customer address 3", order.get("customerAddress3", "")),
        ("Postal code/city/state", order.get("postalCityState", "")),
        ("Primary phone", order.get("primaryPhone", "")),
        ("Secondary phone", order.get("secondaryPhone", "")),
        ("Mobile phone", order.get("mobile", "")),
        ("Email", order.get("email", "")),
        ("Service provider", order.get("serviceProvider", "")),
        ("Service product", order.get("serviceProduct", "")),
        ("Originating store", order.get("originatingStore", "")),
        ("Order number", order.get("orderNumber", "")),
        ("Delivery order number", order.get("deliveryOrderNumber", "")),
        ("Order attachment exists", "No"),
        ("Delivery instructions", ""),
    ]
    
    for label, value in fields:
        draw_field_row(c, x, y, label, value, label_w, line_w)
        y -= lh
    
    # Booked service dates
    y -= 3*mm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Booked service dates")
    y -= lh
    
    for date_str in order.get("serviceDates", []):
        c.setFont("Helvetica", 8)
        c.drawString(x, y, date_str)
        y -= 6*mm


def draw_service_report_p2(c, w, h, order, report):
    """Side 2/3 — Udfyldt af serviceudbyder."""
    draw_header(c, w, h, 2)
    
    x = 20*mm
    y = h - 32*mm
    lh = 8*mm
    label_w = 80*mm
    line_w = 80*mm
    
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Filled in by service provider")
    y -= lh
    
    # Start/slut tid
    draw_field_row(c, x, y, "Service actual start date/time",
                   report.get("startTime", ""), label_w, line_w)
    y -= lh
    draw_field_row(c, x, y, "Service actual end date/time",
                   report.get("endTime", ""), label_w, line_w)
    y -= lh
    
    # Additional services
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Additional services needed?")
    draw_checkbox(c, x + 90*mm, y, "Yes", report.get("additionalServices") == True)
    draw_checkbox(c, x + 115*mm, y, "No", report.get("additionalServices") != True)
    y -= lh
    
    # Hours
    draw_field_row(c, x, y, "Hours to complete service",
                   report.get("hoursSpent", ""), label_w, 30*mm)
    c.setFont("Helvetica", 9)
    c.drawString(x + label_w + 35*mm, y, "hours")
    y -= lh
    
    # Who performed
    draw_field_row(c, x, y, "Who performed the service?(team/name)",
                   report.get("teamName", ""), label_w, line_w)
    y -= lh
    
    # Number of assemblers
    draw_field_row(c, x, y, "Number of assemblers",
                   report.get("numAssemblers", ""), label_w, line_w)
    y -= lh
    
    # SP contact IKEA
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "SP have been in contact with IKEA?")
    draw_checkbox(c, x + 90*mm, y, "Yes", report.get("contactedIkea") == True)
    draw_checkbox(c, x + 115*mm, y, "No", report.get("contactedIkea") != True)
    y -= lh
    
    # Customer service ref
    draw_field_row(c, x, y, "Customer service reference id",
                   report.get("ikeaRef", ""), label_w, line_w)
    y -= lh * 1.5
    
    # Status checkboxes
    status = report.get("serviceStatus", "")
    draw_checkbox(c, x, y, "Service completed", status == "completed")
    y -= lh
    draw_checkbox(c, x, y, "Service failed", status == "failed")
    y -= lh
    draw_checkbox(c, x, y, "Service incomplete", status == "incomplete")
    y -= lh * 1.5
    
    # Failed reason codes
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Select failed reason code")
    y -= lh * 0.8
    
    fail_reasons = report.get("failedReasons", [])
    left_fails = [("Customer not home", "customerNotHome"), ("No/Not enough capacity", "noCapacity"), ("Payment problems", "paymentProblems")]
    right_fails = [("Articles missing", "articlesMissing"), ("Inappropriate service conditions", "inappropriateConditions")]
    
    for i, (label, key) in enumerate(left_fails):
        draw_checkbox(c, x, y - i*lh*0.9, label, key in fail_reasons)
    for i, (label, key) in enumerate(right_fails):
        draw_checkbox(c, x + 90*mm, y - i*lh*0.9, label, key in fail_reasons)
    y -= lh * 3
    
    # Incomplete reason codes
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Select incomplete reason code")
    y -= lh * 0.8
    
    inc_reasons = report.get("incompleteReasons", [])
    left_inc = [("Articles missing", "articlesMissing"), ("Damaged articles", "damagedArticles"), ("Sales error", "salesError"), ("Installation error", "installError")]
    right_inc = [("Incorrect articles", "incorrectArticles"), ("Pre measurements not correct", "preNotCorrect"), ("Payment problems", "paymentProblems"), ("Changed mind", "changedMind")]
    
    for i, (label, key) in enumerate(left_inc):
        draw_checkbox(c, x, y - i*lh*0.9, label, key in inc_reasons)
    for i, (label, key) in enumerate(right_inc):
        draw_checkbox(c, x + 90*mm, y - i*lh*0.9, label, key in inc_reasons)
    y -= lh * 4.5
    
    # Comments
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Comments")
    y -= 5*mm
    
    comments = report.get("comments", "")
    if comments:
        c.setFont("Helvetica", 9)
        # Wrap tekst
        words = comments.split()
        line = ""
        for word in words:
            if c.stringWidth(line + word, "Helvetica", 9) < 160*mm:
                line += word + " "
            else:
                c.drawString(x, y, line.strip())
                y -= 5*mm
                line = word + " "
        if line:
            c.drawString(x, y, line.strip())
    
    # Kommentarlinjer
    for _ in range(4):
        y -= 6*mm
        c.setLineWidth(0.4)
        c.line(x, y, w - 20*mm, y)
    
    y -= lh
    # Satisfaction
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "The service was without any complaints and\nperformed to the satisfaction of the customer")
    satisfaction = report.get("satisfaction", False)
    draw_checkbox(c, x + 115*mm, y, "Yes", satisfaction == True)
    draw_checkbox(c, x + 135*mm, y, "No", satisfaction != True)
    
    # Underskrifter
    y -= lh * 3
    c.setLineWidth(0.6)
    
    # Dato
    c.line(x, y, x + 35*mm, y)
    c.setFont("Helvetica", 8)
    c.drawString(x, y - 4*mm, "Date")
    if report.get("completedAt"):
        try:
            d = datetime.fromisoformat(report["completedAt"])
            c.drawString(x, y + 2, d.strftime("%d-%m-%Y"))
        except:
            pass
    
    # Montør signatur
    c.line(x + 45*mm, y, x + 120*mm, y)
    c.drawString(x + 45*mm, y - 4*mm, "Service provider signature")
    
    # Indsæt montør-signatur billede hvis tilgængeligt
    if report.get("techSignatureData"):
        try:
            sig_bytes = base64.b64decode(report["techSignatureData"].split(",")[-1])
            sig_buf = BytesIO(sig_bytes)
            c.drawImage(sig_buf, x + 45*mm, y + 1, width=70*mm, height=15*mm, 
                       preserveAspectRatio=True, mask='auto')
        except:
            pass
    
    # Kunde signatur
    c.line(x + 130*mm, y, w - 20*mm, y)
    c.drawString(x + 130*mm, y - 4*mm, "Customer signature")
    
    if report.get("customerSignatureData"):
        try:
            sig_bytes = base64.b64decode(report["customerSignatureData"].split(",")[-1])
            sig_buf = BytesIO(sig_bytes)
            c.drawImage(sig_buf, x + 130*mm, y + 1, width=35*mm, height=15*mm,
                       preserveAspectRatio=True, mask='auto')
        except:
            pass


def draw_service_report_p3(c, w, h, order):
    """Side 3/3 — Artikelliste."""
    draw_header(c, w, h, 3)
    
    x = 20*mm
    y = h - 35*mm
    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Service articles")
    y -= 8*mm
    
    articles = order.get("articles", [])
    if not articles:
        c.setFont("Helvetica", 9)
        c.drawString(x, y, "Ingen artikler")
        return
    
    # Tabel headers
    col_widths = [65*mm, 18*mm, 16*mm, 18*mm, 22*mm, 10*mm, 16*mm]
    headers = ["Description", "Net\nprice", "VAT", "Gross\nprice", "Item no", "Qty", "Error\ncode"]
    
    # Tegn header
    cx = x
    c.setFont("Helvetica-Bold", 8)
    header_y = y
    for i, (header, cw) in enumerate(zip(headers, col_widths)):
        lines = header.split('\n')
        for j, line in enumerate(lines):
            c.drawString(cx + 1*mm, header_y - j*4*mm, line)
        cx += cw
    
    y -= 10*mm
    c.setLineWidth(0.4)
    c.line(x, y + 2*mm, w - 20*mm, y + 2*mm)
    
    # Artikelrækker
    c.setFont("Helvetica", 8)
    for article in articles:
        if y < 30*mm:  # Ny side hvis vi løber tør
            c.showPage()
            y = h - 30*mm
        
        desc = article.get("description", "")
        # Wrap beskrivelse hvis den er lang
        max_desc_w = 63*mm
        if c.stringWidth(desc, "Helvetica", 8) > max_desc_w:
            words = desc.split()
            line1, line2 = "", ""
            for word in words:
                if c.stringWidth(line1 + word, "Helvetica", 8) < max_desc_w:
                    line1 += word + " "
                else:
                    line2 += word + " "
            c.drawString(x + 1*mm, y, line1.strip())
            if line2:
                c.drawString(x + 1*mm, y - 4*mm, line2.strip())
        else:
            c.drawString(x + 1*mm, y, desc)
        
        vals = [
            article.get("netPrice", ""),
            article.get("vat", ""),
            article.get("grossPrice", ""),
            article.get("itemNo", ""),
            article.get("qty", ""),
            article.get("errorCode", ""),
        ]
        
        cx = x + col_widths[0]
        for val, cw in zip(vals, col_widths[1:]):
            c.drawString(cx + 1*mm, y, str(val))
            cx += cw
        
        y -= 7*mm if c.stringWidth(article.get("description",""), "Helvetica", 8) > max_desc_w else 6*mm


# ── ANSVARSFRASKRIVELSE PDF ────────────────────────────────────────────────────

def generate_disclaimer(order_data, report_data, output_path=None):
    """
    Genererer ansvarsfraskrivelse PDF identisk med originaldokument (billede 2).
    """
    buffer = BytesIO()
    target = output_path or buffer
    
    c = canvas.Canvas(target, pagesize=A4)
    w, h = A4
    
    x = 20*mm
    y = h - 25*mm
    
    # ── TITEL ────────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x, y, "Møbelmontering – Ansvarsfraskrivelse")
    y -= 8*mm
    
    # ── UNDERTITEL ───────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Ved fravalg af vægforankring af produkt med monteringsservice.")
    y -= 8*mm
    
    # ── BRØDTEKST ────────────────────────────────────────────────────────────
    paragraphs = [
        "Hos IKEA har sikkerhed højest prioritet, både når der udvikles, samles og monteres produkter. For at møblerne skal være så sikre som muligt at færdes i og omkring, kræver enkelte produkter fastgørelse til væg for at undgå at de vælter og går i stykker eller skader mennesker, dyr og andet.",
        
        "Når du bestiller Monteringsservice i IKEA, vil vi gerne have at du skal føle dig tryg ved at produkterne er sikre at anvende, og derfor indebærer det altid at produkter der kræver fastgørelse til væg, også bliver det.",
        
        "Montøren har, før opstart af monteringen, informeret dig om, at der i din service indgår et eller flere produkter der kræver fastgørelse i væg.",
        
        "Du har ønsket, ikke at lade montørerne udføre denne del af servicen, og det kan derfor medføre at produktet/produkterne vælter og forårsager alvorlig skade på mennesker, dyr og/eller andet. Ydermere vil produkt og servicegaranti frafalde hvis skaden opstår grundet manglende fastgørelse til væg.",
        
        "IKEA og/eller montøren kan derfor ikke tage noget ansvar for de skader der kan indtræffe på grund af at produktet ikke er fastgjort i væggen.",
        
        "Du har, med fravalget af vægforankring selv ansvaret for eventuelle skader (både direkte og indirekte) som kan opstå som følge af dette fravalg.",
    ]
    
    c.setFont("Helvetica", 9.5)
    line_height = 5.2*mm
    
    for para in paragraphs:
        y -= 2*mm
        # Word wrap
        words = para.split()
        line = ""
        max_w = w - 40*mm
        
        for word in words:
            test = line + word + " "
            if c.stringWidth(test, "Helvetica", 9.5) < max_w:
                line = test
            else:
                c.drawString(x, y, line.rstrip())
                y -= line_height
                line = word + " "
        
        if line.strip():
            c.drawString(x, y, line.rstrip())
            y -= line_height
    
    y -= 5*mm
    
    # Ordrenummer linje
    c.setFont("Helvetica", 9.5)
    order_line = f"Monteringsservice er i dag udført ifølge IKEA ordrenr.: {order_data.get('orderNumber', '')}"
    c.drawString(x, y, order_line)
    y -= 10*mm
    
    # ── BEKRÆFTELSESTEKST ─────────────────────────────────────────────────────
    c.setFont("Helvetica", 9.5)
    confirm_text = "Med din underskrift bekræfter du som kunde hermed at du er indforstået med indholdet i denne ansvarsfraskrivelse."
    words = confirm_text.split()
    line = ""
    for word in words:
        test = line + word + " "
        if c.stringWidth(test, "Helvetica", 9.5) < w - 40*mm:
            line = test
        else:
            c.drawString(x, y, line.rstrip())
            y -= 5.5*mm
            line = word + " "
    if line.strip():
        c.drawString(x, y, line.rstrip())
    y -= 12*mm
    
    # ── FELTER ───────────────────────────────────────────────────────────────
    field_line_w = w - 40*mm
    
    def draw_disclaimer_field(label, value="", y_pos=0):
        c.setFont("Helvetica", 9.5)
        c.drawString(x, y_pos, f"{label}:")
        c.setLineWidth(0.5)
        c.line(x, y_pos - 2, x + field_line_w, y_pos - 2)
        if value:
            c.setFont("Helvetica", 9.5)
            c.drawString(x + 2, y_pos - 1, value)
        return y_pos - 12*mm
    
    # By (hent fra adresse)
    city = ""
    postal = order_data.get("postalCityState", "")
    if postal:
        parts = postal.split(" ", 1)
        city = parts[1] if len(parts) > 1 else postal
    
    y = draw_disclaimer_field("By", city, y)
    
    # Dato
    date_str = ""
    if report_data.get("completedAt"):
        try:
            d = datetime.fromisoformat(report_data["completedAt"])
            date_str = d.strftime("%d-%m-%Y")
        except:
            date_str = datetime.now().strftime("%d-%m-%Y")
    else:
        date_str = datetime.now().strftime("%d-%m-%Y")
    
    y = draw_disclaimer_field("Dato", date_str, y)
    y = draw_disclaimer_field("Navn (med blokbogstaver)", "", y)
    
    # Kunde signatur
    c.setFont("Helvetica", 9.5)
    c.drawString(x, y, "Kunde signatur:")
    c.setLineWidth(0.5)
    c.line(x, y - 2, x + field_line_w, y - 2)
    
    if report_data.get("disclaimerSignatureData"):
        try:
            sig_bytes = base64.b64decode(report_data["disclaimerSignatureData"].split(",")[-1])
            sig_buf = BytesIO(sig_bytes)
            c.drawImage(sig_buf, x, y - 20*mm, width=80*mm, height=18*mm,
                       preserveAspectRatio=True, mask='auto')
        except:
            pass
    
    y -= 20*mm
    
    # Montør signatur
    c.setFont("Helvetica", 9.5)
    c.drawString(x, y, "Montør signatur:")
    c.setLineWidth(0.5)
    c.line(x, y - 2, x + field_line_w, y - 2)
    
    if report_data.get("techSignatureData"):
        try:
            sig_bytes = base64.b64decode(report_data["techSignatureData"].split(",")[-1])
            sig_buf = BytesIO(sig_bytes)
            c.drawImage(sig_buf, x, y - 20*mm, width=80*mm, height=18*mm,
                       preserveAspectRatio=True, mask='auto')
        except:
            pass
    
    c.save()
    
    if output_path:
        return output_path
    else:
        buffer.seek(0)
        return buffer.read()


# ── MAIN — Parse og test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    
    test_pdfs = [
        "/mnt/user-data/uploads/Team_3_Service_Order_Report_08-06-2026.pdf",
        "/mnt/user-data/uploads/Team_2_Service_Order_Report_08-06-2026.pdf",
    ]
    
    all_orders = []
    for pdf_path in test_pdfs:
        if os.path.exists(pdf_path):
            print(f"\nParser: {pdf_path.split('/')[-1]}")
            orders = parse_pdf_orders(pdf_path)
            print(f"  Fandt {len(orders)} ordre(r)")
            for o in orders:
                print(f"  - #{o['orderNumber']}: {o['customerName']} ({o['postalCityState']})")
                print(f"    Artikler: {len(o['articles'])}")
            all_orders.extend(orders)
    
    if all_orders:
        # Generer test rapport PDF for første ordre
        test_report = {
            "teamName": "Team 2",
            "startTime": "08:30",
            "endTime": "11:45",
            "hoursSpent": "3.25",
            "numAssemblers": "2",
            "serviceStatus": "completed",
            "additionalServices": False,
            "contactedIkea": False,
            "ikeaRef": "",
            "comments": "Service udført uden problemer. Kunde tilfreds.",
            "satisfaction": True,
            "failedReasons": [],
            "incompleteReasons": [],
            "wallMountRefused": False,
            "completedAt": datetime.now().isoformat(),
        }
        
        # Gem servicerapport
        out_path = "/mnt/user-data/outputs/test_servicerapport.pdf"
        generate_service_report(all_orders[0], test_report, out_path)
        print(f"\n✓ Servicerapport gemt: {out_path}")
        
        # Gem ansvarsfraskrivelse
        disclaimer_report = {**test_report, "wallMountRefused": True}
        out_path2 = "/mnt/user-data/outputs/test_ansvarsfraskrivelse.pdf"
        generate_disclaimer(all_orders[0], disclaimer_report, out_path2)
        print(f"✓ Ansvarsfraskrivelse gemt: {out_path2}")
        
        # Gem parsed data som JSON (bruges af appen)
        json_out = "/mnt/user-data/outputs/parsed_orders.json"
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(all_orders, f, ensure_ascii=False, indent=2)
        print(f"✓ Parsed ordrer gemt: {json_out}")
        print(f"\nTotal: {len(all_orders)} ordrer parsed")
