#!/usr/bin/env python3
"""
USA Docs Filing Instructions Generator
Generates a companion PDF with mailing address, document checklist, and fee info.
Usage: python generate_instructions.py <form_id> <answers_json> <output_pdf>
"""
import sys
import json
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, ListFlowable, ListItem

# Filing instructions data per form
FORM_DATA = {
    "i90": {
        "title": "I-90 — Renew or Replace Green Card",
        "uscis_fee": "$465",
        "biometric_fee": "Included",
        "mailing": {
            "online": "USCIS recommends filing online at https://www.uscis.gov/i-90",
            "mail_address": "USCIS Phoenix Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-90\nP.O. Box 21262\nPhoenix, AZ 85036\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-90 (Box 21262)\n1820 E. Skyharbor Circle S, Suite 100\nPhoenix, AZ 85034"
        },
        "processing_time": "6-18 months",
        "documents": [
            "Copy of your current (or expired) green card — front and back",
            "2 passport-style photos (2x2 inches, white background, taken within 30 days)",
            "Government-issued photo ID (driver's license or passport)",
            "If name changed: marriage certificate, divorce decree, or court order",
            "If card was lost/stolen: police report (if available)",
            "Check or money order for $465 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "File at least 6 months before your card expires",
            "You can file online — it's faster than mailing",
            "Keep your receipt notice (Form I-797C) — it extends your green card for 24 months",
            "Do NOT send original documents unless specifically requested"
        ]
    },
    "i130": {
        "title": "I-130 — Petition for Alien Relative",
        "uscis_fee": "$675",
        "biometric_fee": "None",
        "mailing": {
            "online": "Can be filed online at https://www.uscis.gov/i-130",
            "mail_address": "USCIS Chicago Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-130\nP.O. Box 804625\nChicago, IL 60680-4107\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-130\n131 South Dearborn - 3rd Floor\nChicago, IL 60603-5517"
        },
        "processing_time": "12-24 months",
        "documents": [
            "Proof of U.S. citizenship or permanent residence (birth certificate, naturalization certificate, passport, or green card copy)",
            "Proof of relationship (marriage certificate, birth certificate of child, etc.)",
            "2 passport-style photos of the petitioner",
            "2 passport-style photos of the beneficiary (the person you're bringing)",
            "Copy of petitioner's government-issued photo ID",
            "If married: marriage certificate AND proof of termination of any prior marriages",
            "Check or money order for $675 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "You can file online — it's faster than mailing",
            "Include as much supporting evidence of the relationship as possible",
            "If filing for a spouse, include photos of you together, joint leases, shared bank accounts",
            "Processing times vary significantly by category and relationship"
        ]
    },
    "n400": {
        "title": "N-400 — Application for U.S. Citizenship",
        "uscis_fee": "$760",
        "biometric_fee": "Included",
        "mailing": {
            "online": "USCIS recommends filing online at https://www.uscis.gov/n-400",
            "mail_address": "USCIS Dallas Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: N-400\nP.O. Box 660060\nDallas, TX 75266\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: N-400\n2501 S. State Hwy 121 Business, Suite 400\nLewisville, TX 75067"
        },
        "processing_time": "8-14 months",
        "documents": [
            "Copy of your green card — front and back",
            "2 passport-style photos (2x2 inches, white background)",
            "Copy of your government-issued photo ID",
            "If married to U.S. citizen: marriage certificate + spouse's proof of citizenship",
            "If name changed: court order or marriage certificate",
            "Evidence of any travel outside the U.S. during the last 5 years",
            "Tax returns for the last 5 years (or 3 years if married to U.S. citizen)",
            "Check or money order for $760 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "You can file up to 90 days before you meet the residency requirement",
            "Study for the civics and English test — free materials at uscis.gov/citizenship",
            "Be honest on all questions — lying can permanently bar you from citizenship",
            "Bring your green card to your interview appointment"
        ]
    },
    "i485": {
        "title": "I-485 — Adjustment of Status (Green Card)",
        "uscis_fee": "$1,440 (includes biometrics)",
        "biometric_fee": "Included",
        "mailing": {
            "online": "Can be filed online at https://www.uscis.gov/i-485",
            "mail_address": "USCIS Chicago Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-485\nP.O. Box 805887\nChicago, IL 60680-4120\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-485\n131 South Dearborn - 3rd Floor\nChicago, IL 60603-5517"
        },
        "processing_time": "12-36 months",
        "documents": [
            "Copy of your birth certificate (with English translation if not in English)",
            "Copy of your passport (biographic page + all visa stamps)",
            "Copy of your I-94 arrival/departure record",
            "2 passport-style photos",
            "Medical examination results (Form I-693) from a USCIS-designated civil surgeon",
            "Proof of approved I-130 or I-140 (receipt notice or approval notice)",
            "Affidavit of Support (Form I-864) from your petitioner",
            "Police clearance records for any country you lived in 6+ months since age 16",
            "Check or money order for $1,440 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "The medical exam (I-693) must be done by a USCIS civil surgeon — find one at uscis.gov",
            "You can file I-765 (work permit) and I-131 (travel document) at the same time for FREE",
            "Do NOT leave the U.S. without advance parole while this is pending",
            "Keep all receipt notices safe — you'll need them"
        ]
    },
    "i765": {
        "title": "I-765 — Work Permit (EAD)",
        "uscis_fee": "$520",
        "biometric_fee": "Included",
        "mailing": {
            "online": "USCIS recommends filing online at https://www.uscis.gov/i-765",
            "mail_address": "USCIS Phoenix Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-765\nP.O. Box 21281\nPhoenix, AZ 85036\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-765 (Box 21281)\n1820 E. Skyharbor Circle S, Suite 100\nPhoenix, AZ 85034"
        },
        "processing_time": "3-7 months",
        "documents": [
            "Copy of a government-issued photo ID",
            "2 passport-style photos (2x2 inches, white background)",
            "Copy of your I-94 arrival/departure record",
            "Copy of your most recent EAD card (if renewing)",
            "Copy of the receipt notice for any pending USCIS application this EAD is based on",
            "Check or money order for $520 payable to 'U.S. Department of Homeland Security' (FREE if filed with I-485)"
        ],
        "tips": [
            "File online for faster processing",
            "If filed with a pending I-485, the fee is waived",
            "Renew at least 6 months before your current EAD expires",
            "Your receipt notice auto-extends your EAD for up to 540 days while the renewal is pending"
        ]
    },
    "i821d": {
        "title": "I-821D — DACA Renewal",
        "uscis_fee": "$495 (includes I-765 EAD and biometrics)",
        "biometric_fee": "Included",
        "mailing": {
            "online": "Can be filed online at https://www.uscis.gov/i-821d",
            "mail_address": "USCIS Dallas Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-821D\nP.O. Box 660867\nDallas, TX 75266\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-821D\n2501 S. State Hwy 121 Business, Suite 400\nLewisville, TX 75067"
        },
        "processing_time": "2-8 months",
        "documents": [
            "Copy of your previous EAD card (front and back)",
            "Copy of your most recent DACA approval notice (I-797)",
            "Completed I-765 form (work permit — filed together)",
            "2 passport-style photos",
            "Copy of a government-issued photo ID",
            "Check or money order for $495 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "File your renewal 150-120 days before your current DACA expires",
            "Always file I-821D together with I-765 (work permit)",
            "Do NOT let your DACA expire — late renewals may cause gaps in work authorization",
            "Keep copies of everything you send to USCIS"
        ]
    },
    "i751": {
        "title": "I-751 — Remove Conditions on Green Card",
        "uscis_fee": "$750",
        "biometric_fee": "Included",
        "mailing": {
            "online": "Can be filed online at https://www.uscis.gov/i-751",
            "mail_address": "USCIS Phoenix Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-751\nP.O. Box 21300\nPhoenix, AZ 85036\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-751 (Box 21300)\n1820 E. Skyharbor Circle S, Suite 100\nPhoenix, AZ 85034"
        },
        "processing_time": "18-30 months",
        "documents": [
            "Copy of your conditional green card (front and back)",
            "Proof of bona fide marriage: joint lease/mortgage, joint bank statements, joint tax returns, insurance policies, birth certificates of children, photos together",
            "If filing jointly: spouse must also sign the form",
            "If filing alone (waiver): evidence of abuse, divorce decree, or hardship documentation",
            "2 passport-style photos",
            "Check or money order for $750 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "File within the 90-day window before your card expires",
            "The more evidence of a real marriage, the better — include as much as possible",
            "Your receipt notice (I-797C) extends your green card for 24 months",
            "If divorced, you can still file with a waiver — consult a lawyer for complex cases"
        ]
    },
    "i131": {
        "title": "I-131 — Travel Document",
        "uscis_fee": "$630",
        "biometric_fee": "Included for Reentry Permit",
        "mailing": {
            "online": "Can be filed online at https://www.uscis.gov/i-131",
            "mail_address": "USCIS Dallas Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-131\nP.O. Box 660867\nDallas, TX 75266\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-131\n2501 S. State Hwy 121 Business, Suite 400\nLewisville, TX 75067"
        },
        "processing_time": "3-10 months",
        "documents": [
            "Copy of your green card or pending I-485 receipt notice",
            "Copy of your passport biographic page",
            "2 passport-style photos",
            "Explanation of why you need to travel",
            "Copy of any travel tickets or itinerary (if available)",
            "Check or money order for $630 payable to 'U.S. Department of Homeland Security' (FREE if filed with I-485)"
        ],
        "tips": [
            "If you have a pending I-485, DO NOT travel without advance parole",
            "The fee is waived if filed concurrently with I-485",
            "For reentry permit: you must be physically in the U.S. when you file and for biometrics",
            "Apply well before your planned travel date"
        ]
    },
    "i129f": {
        "title": "I-129F — Fiancé(e) Visa (K-1)",
        "uscis_fee": "$675",
        "biometric_fee": "None for petitioner",
        "mailing": {
            "online": "Must be filed by mail — NOT available online",
            "mail_address": "USCIS Dallas Lockbox\nFor U.S. Postal Service:\nUSCIS\nAttn: I-129F\nP.O. Box 660151\nDallas, TX 75266\n\nFor FedEx/UPS/DHL:\nUSCIS\nAttn: I-129F\n2501 S. State Hwy 121 Business, Suite 400\nLewisville, TX 75067"
        },
        "processing_time": "7-10 months",
        "documents": [
            "Proof of U.S. citizenship (birth certificate, passport, or naturalization certificate)",
            "Proof you met in person within the last 2 years (photos, travel receipts, boarding passes)",
            "2 passport-style photos of the petitioner",
            "2 passport-style photos of the fiancé(e)",
            "Evidence of your relationship (messages, call logs, photos, letters)",
            "Copy of fiancé(e)'s passport biographic page",
            "If either was previously married: proof of termination (divorce decree, death certificate)",
            "Form G-325A (Biographic Information) for both petitioner and fiancé(e)",
            "Check or money order for $675 payable to 'U.S. Department of Homeland Security'"
        ],
        "tips": [
            "You MUST have met your fiancé(e) in person within the last 2 years",
            "This form must be mailed — it cannot be filed online",
            "After approval, your fiancé(e) must apply for the K-1 visa at a U.S. embassy/consulate",
            "You must marry within 90 days of your fiancé(e) entering the U.S."
        ]
    }
}


def generate_instructions(form_id, answers, output_path):
    """Generate a filing instructions PDF"""
    if form_id not in FORM_DATA:
        raise ValueError(f"Unknown form: {form_id}")
    
    data = FORM_DATA[form_id]
    
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=20, textColor=HexColor('#1a365d'),
        spaceAfter=6
    )
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'],
        fontSize=14, textColor=HexColor('#2563eb'),
        spaceBefore=16, spaceAfter=8
    )
    body_style = ParagraphStyle(
        'CustomBody', parent=styles['Normal'],
        fontSize=11, leading=16, spaceAfter=6
    )
    note_style = ParagraphStyle(
        'NoteStyle', parent=styles['Normal'],
        fontSize=10, leading=14, textColor=HexColor('#666666'),
        leftIndent=12, spaceAfter=4
    )
    tip_style = ParagraphStyle(
        'TipStyle', parent=styles['Normal'],
        fontSize=10, leading=14, textColor=HexColor('#065f46'),
        spaceAfter=4,
        bulletIndent=0, leftIndent=18
    )
    warn_style = ParagraphStyle(
        'WarnStyle', parent=styles['Normal'],
        fontSize=10, leading=14, textColor=HexColor('#92400e'),
        spaceAfter=4
    )
    
    story = []
    
    # Header
    story.append(Paragraph("USA Docs — Filing Instructions", title_style))
    story.append(Paragraph(data["title"], ParagraphStyle(
        'SubTitle', parent=styles['Normal'],
        fontSize=14, textColor=HexColor('#4a5568'), spaceAfter=4
    )))
    story.append(Paragraph(
        f"Prepared on {datetime.now().strftime('%B %d, %Y')}",
        ParagraphStyle('DateStyle', parent=styles['Normal'],
                       fontSize=10, textColor=HexColor('#999999'), spaceAfter=12)
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#e2e8f0')))
    story.append(Spacer(1, 12))
    
    # Disclaimer
    story.append(Paragraph(
        "<b>IMPORTANT:</b> USA Docs is a document preparation service. We are not lawyers. "
        "We are not affiliated with USCIS or any government agency. We do not provide legal advice. "
        "This checklist is for informational purposes. For legal questions, consult an immigration attorney.",
        warn_style
    ))
    story.append(Spacer(1, 12))
    
    # Fees section
    story.append(Paragraph("USCIS Filing Fees", heading_style))
    fee_data = [
        ["Fee Type", "Amount", "Notes"],
        ["USCIS Filing Fee", data["uscis_fee"], "Pay to 'U.S. Department of Homeland Security'"],
        ["Biometrics", data["biometric_fee"], "Fingerprinting appointment"],
        ["USA Docs Prep Fee", "PAID", "Your document preparation fee"],
    ]
    fee_table = Table(fee_data, colWidths=[2 * inch, 1.5 * inch, 3 * inch])
    fee_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2563eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#f8fafc')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
    ]))
    story.append(fee_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "The USCIS filing fee is separate from the USA Docs preparation fee. "
        "Pay by check or money order — do NOT send cash.",
        note_style
    ))
    story.append(Spacer(1, 12))
    
    # Where to file
    story.append(Paragraph("Where to File", heading_style))
    story.append(Paragraph(f"<b>Online:</b> {data['mailing']['online']}", body_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>By Mail:</b>", body_style))
    for line in data["mailing"]["mail_address"].split("\n"):
        story.append(Paragraph(line, note_style))
    story.append(Spacer(1, 12))
    
    # Processing time
    story.append(Paragraph("Estimated Processing Time", heading_style))
    story.append(Paragraph(
        f"<b>{data['processing_time']}</b> — Processing times vary. "
        "Check current estimates at uscis.gov/processing-times",
        body_style
    ))
    story.append(Spacer(1, 12))
    
    # Document checklist
    story.append(Paragraph("Document Checklist", heading_style))
    story.append(Paragraph(
        "Gather these documents before mailing your application. Check each item off as you prepare it:",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    for i, doc_item in enumerate(data["documents"], 1):
        story.append(Paragraph(
            f"{'<font color=\"#2563eb\">[  ]</font>'} {doc_item}",
            ParagraphStyle('CheckItem', parent=styles['Normal'],
                           fontSize=11, leading=18, leftIndent=12, spaceAfter=4)
        ))
    
    story.append(Spacer(1, 12))
    
    # Tips
    story.append(Paragraph("Important Tips", heading_style))
    for tip in data["tips"]:
        story.append(Paragraph(f"<bullet>&bull;</bullet> {tip}", tip_style))
    
    story.append(Spacer(1, 16))
    
    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#e2e8f0')))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "USA Docs | usa-docs.com | Document Preparation Service<br/>"
        "We are not lawyers. We are not a government agency. We do not provide legal advice.",
        ParagraphStyle('Footer', parent=styles['Normal'],
                       fontSize=9, textColor=HexColor('#999999'), alignment=1)
    ))
    
    doc.build(story)
    return {"success": True, "output": output_path}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python generate_instructions.py <form_id> <answers_json_file> <output_pdf>")
        sys.exit(1)
    
    form_id = sys.argv[1]
    with open(sys.argv[2]) as f:
        answers = json.load(f)
    output_path = sys.argv[3]
    
    result = generate_instructions(form_id, answers, output_path)
    print(json.dumps(result, indent=2))
