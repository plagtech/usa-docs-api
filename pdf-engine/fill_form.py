#!/usr/bin/env python3
"""
USA Docs PDF Filler
Downloads a blank USCIS form and fills it with customer answers.
Usage: python fill_form.py <form_id> <answers_json> <output_pdf>
"""
import sys
import json
import os
import re
import urllib.request
import tempfile
from datetime import datetime
from pypdf import PdfReader, PdfWriter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_FILE = os.path.join(SCRIPT_DIR, "mappings", "all-mappings.json")
FORMS_CACHE = os.path.join(SCRIPT_DIR, "forms")

def load_mappings():
    with open(MAPPINGS_FILE, "r") as f:
        return json.load(f)

def get_blank_form(form_id, form_url):
    """Download blank USCIS form (cached locally)"""
    os.makedirs(FORMS_CACHE, exist_ok=True)
    cached = os.path.join(FORMS_CACHE, f"{form_id}.pdf")
    if not os.path.exists(cached):
        print(f"Downloading {form_url}...", file=sys.stderr)
        urllib.request.urlretrieve(form_url, cached)
    return cached

def parse_name(full_name):
    """Split 'First Middle Last' or 'First Last' into components"""
    parts = full_name.strip().split()
    if len(parts) == 0:
        return "", "", ""
    elif len(parts) == 1:
        return parts[0], "", ""
    elif len(parts) == 2:
        return parts[-1], parts[0], ""  # family, given, middle
    else:
        return parts[-1], parts[0], " ".join(parts[1:-1])

def parse_address(address_str):
    """Best-effort parse of a US address string into street, city, state, zip"""
    # Try to match: street, city, state zip
    m = re.match(r'^(.+?),\s*(.+?),?\s*([A-Z]{2})?\s*(\d{5}(?:-\d{4})?)?\s*$', address_str, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3) or "", m.group(4) or ""
    # Fallback: just put everything in street
    return address_str, "", "", ""

def format_date(date_str, fmt="MM/DD/YYYY"):
    """Convert various date formats to MM/DD/YYYY"""
    for parse_fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y"]:
        try:
            dt = datetime.strptime(date_str, parse_fmt)
            if fmt == "MM/DD/YYYY":
                return dt.strftime("%m/%d/%Y")
            return date_str
        except ValueError:
            continue
    return date_str  # Return as-is if we can't parse

def fill_form(form_id, answers, output_path):
    """Fill a USCIS form with customer answers"""
    mappings = load_mappings()
    
    if form_id not in mappings:
        raise ValueError(f"Unknown form: {form_id}")
    
    form_config = mappings[form_id]
    field_map = form_config["field_map"]
    
    # Get blank form
    blank_pdf = get_blank_form(form_id, form_config["form_url"])
    
    reader = PdfReader(blank_pdf)
    writer = PdfWriter()
    # Clone entire PDF including AcroForm
    writer.clone_document_from_reader(reader)
    
    # Build field values dict
    field_values = {}
    errors = []
    
    for question_id, answer_value in answers.items():
        if question_id not in field_map:
            continue
        
        mapping = field_map[question_id]
        mtype = mapping["type"]
        
        try:
            if mtype == "text":
                field_values[mapping["field"]] = answer_value
                
            elif mtype == "date":
                formatted = format_date(answer_value, mapping.get("format", "MM/DD/YYYY"))
                field_values[mapping["field"]] = formatted
                
            elif mtype == "name_split":
                family, given, middle = parse_name(answer_value)
                field_values[mapping["family_name"]] = family
                field_values[mapping["given_name"]] = given
                if middle and "middle_name" in mapping:
                    field_values[mapping["middle_name"]] = middle
                    
            elif mtype == "address_split":
                street, city, state, zipcode = parse_address(answer_value)
                field_values[mapping["street"]] = street
                if city:
                    field_values[mapping["city"]] = city
                if zipcode:
                    field_values[mapping["zip"]] = zipcode
                    
            elif mtype == "checkbox_map":
                if answer_value in mapping["map"]:
                    cb = mapping["map"][answer_value]
                    field_values[cb["field"]] = cb["value"]
                    
            elif mtype == "text_note":
                pass  # Not a fillable field
                
        except Exception as e:
            errors.append(f"Field {question_id}: {str(e)}")
    
    # Use pypdf's built-in form filling
    filled_count = 0
    for page_num in range(len(writer.pages)):
        try:
            writer.update_page_form_field_values(
                writer.pages[page_num],
                field_values,
                auto_regenerate=False
            )
            filled_count += 1
        except Exception as e:
            errors.append(f"Page {page_num}: {str(e)}")
    
    # Flatten the form so it's not editable
    # (optional — some prefer to leave it editable)
    
    with open(output_path, "wb") as out:
        writer.write(out)
    
    return {
        "success": True,
        "fields_mapped": len(field_values),
        "pages": len(reader.pages),
        "errors": errors,
        "output": output_path
    }


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python fill_form.py <form_id> <answers_json_file> <output_pdf>")
        sys.exit(1)
    
    form_id = sys.argv[1]
    with open(sys.argv[2]) as f:
        answers = json.load(f)
    output_path = sys.argv[3]
    
    result = fill_form(form_id, answers, output_path)
    print(json.dumps(result, indent=2))
