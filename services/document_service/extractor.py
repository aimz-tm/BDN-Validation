import re
import spacy
from services.document_service.ocr import extract_text_with_confidence

# Load spaCy model once at module level
nlp = spacy.load("en_core_web_sm")


def extract_with_spacy(text: str) -> dict:
    """
    Use spaCy NER to extract entities as fallback/enhancer.
    Returns dict of detected entities by type.
    """
    doc = nlp(text)
    entities = {}
    for ent in doc.ents:
        if ent.label_ == "GPE":          # Geopolitical — ports, countries
            entities.setdefault("locations", []).append(ent.text)
        elif ent.label_ == "ORG":        # Organisations — suppliers, companies
            entities.setdefault("orgs", []).append(ent.text)
        elif ent.label_ == "DATE":       # Dates
            entities.setdefault("dates", []).append(ent.text)
        elif ent.label_ == "PERSON":     # Names — officers, masters
            entities.setdefault("persons", []).append(ent.text)
    return entities


def extract_fields(file_path: str) -> dict:
    """
    Extract all required BDN fields using regex + spaCy NER.
    Regex is primary. spaCy fills in where regex misses.
    """
    result = extract_text_with_confidence(file_path)
    text       = result["text"]
    confidence = result["confidence"]

    # Run spaCy on full text
    spacy_entities = extract_with_spacy(text)

    def find(patterns, text):
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def find_number(patterns, text):
        val = find(patterns, text)
        if val:
            cleaned = re.sub(r'[^\d.]', '', val.split()[0])
            try:
                return float(cleaned)
            except:
                return None
        return None

    # ── Regex extraction ─────────────────────────────────────────────
    vessel_name = find([
        r'Vessel\s+Name[:\s]+([A-Z0-9 ]+)',
        r'M\.?V\.?\s+([A-Z0-9 ]+)',
    ], text)

    imo = find([
        r'IMO\s+Number[:\s]+(\d{7})',
        r'IMO[:\s]+(\d{7})',
    ], text)

    barge_name = find([
        r'Barge\s+Name[:\s]+([A-Z0-9 ]+)',
        r'Bunker\s+Barge[:\s]+([A-Z0-9 ]+)',
    ], text)

    barge_imo = find([
        r'Barge\s+IMO[:\s]+(\d{7})',
    ], text)

    delivery_date = find([
        r'Delivery\s+Date[:\s]+(\d{1,2}\s+\w+\s+\d{4})',
        r'Date[:\s]+(\d{1,2}\s+\w+\s+\d{4})',
    ], text)

    start_time = find([
        r'Pumping\s+Start\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
        r'Start\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
    ], text)

    end_time = find([
        r'Pumping\s+End\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
        r'End\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
    ], text)

    port = find([
        r'Port\s+of\s+Delivery[:\s]+([A-Za-z ]+)',
        r'Port[:\s]+([A-Za-z ]+)',
    ], text)

    supplier = find([
        r'Supplier[:\s]+([A-Za-z ]+(?:Ltd|Inc|Pte|Corp)?)',
    ], text)

    quantity    = find_number([r'Quantity\s+Delivered[:\s]+([\d.,]+\s*MT)', r'Quantity[:\s]+([\d.,]+)'], text)
    density     = find_number([r'Density[^:]*[:\s]+([\d.]+)\s*kg', r'Density[^:]*[:\s]+([\d.]+)'], text)
    sulphur     = find_number([r'Sulphur\s+Content[:\s]+([\d.]+)', r'Sulphur[:\s]+([\d.]+)'], text)
    flashpoint  = find_number([r'Flashpoint[:\s]+([\d.]+)', r'Flash\s+Point[:\s]+([\d.]+)'], text)

    # ── spaCy fallbacks ──────────────────────────────────────────────
    # Use spaCy only if regex failed
    if not port and spacy_entities.get("locations"):
        port = spacy_entities["locations"][0]

    if not supplier and spacy_entities.get("orgs"):
        supplier = spacy_entities["orgs"][0]

    if not delivery_date and spacy_entities.get("dates"):
        delivery_date = spacy_entities["dates"][0]

    return {
        "vessel_name":      vessel_name,
        "imo":              imo,
        "barge_name":       barge_name,
        "barge_imo":        barge_imo,
        "delivery_date":    delivery_date,
        "start_time":       start_time,
        "end_time":         end_time,
        "port":             port,
        "supplier":         supplier,
        "quantity_mt":      quantity,
        "density":          density,
        "sulphur_content":  sulphur,
        "flashpoint":       flashpoint,
        "ocr_confidence":   confidence,
        "spacy_entities":   spacy_entities   # kept for transparency
    }