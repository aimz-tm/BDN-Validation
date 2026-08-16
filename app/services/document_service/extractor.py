import re
from app.services.document_service.ocr import extract_text_with_confidence

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover
    from difflib import SequenceMatcher
    class _FuzzFallback:
        @staticmethod
        def token_sort_ratio(a: str, b: str) -> float:
            a_sorted = " ".join(sorted(a.split()))
            b_sorted = " ".join(sorted(b.split()))
            return SequenceMatcher(None, a_sorted, b_sorted).ratio() * 100.0
    fuzz = _FuzzFallback()

try:
    import spacy  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    spacy = None

nlp = None
if spacy is not None:
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        nlp = None


def extract_with_spacy(text: str) -> dict:
    """
    Use spaCy NER to extract entities as fallback/enhancer.
    Returns dict of detected entities by type.
    """
    if nlp is None:
        return {}
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

    def find_fuzzy(labels, text, threshold=75.0):
        lines = text.split('\n')
        best_val = None
        best_score = 0
        for line in lines:
            line = line.strip()
            if not line: continue
            
            parts = re.split(r'[:;|\t]+', line, maxsplit=1)
            if len(parts) == 2:
                key, val = parts[0].strip(), parts[1].strip()
                if val:
                    for label in labels:
                        score = fuzz.token_sort_ratio(label.lower(), key.lower())
                        if score >= threshold and score > best_score:
                            best_score = score
                            best_val = val
            else:
                for label in labels:
                    label_words = label.split()
                    line_words = line.split()
                    if len(line_words) > len(label_words):
                        potential_key = " ".join(line_words[:len(label_words)])
                        potential_val = " ".join(line_words[len(label_words):])
                        score = fuzz.token_sort_ratio(label.lower(), potential_key.lower())
                        if score >= threshold and score > best_score:
                            best_score = score
                            best_val = potential_val
        return best_val

    def find(patterns, labels, text):
        val = None
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                break
        if not val and labels:
            val = find_fuzzy(labels, text)
        return val

    def find_number(patterns, labels, text):
        val = find(patterns, labels, text)
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
    ], ["Vessel Name", "Ship Name", "Receiving Vessel", "MV", "M.V."], text)

    imo = find([
        r'IMO\s+Number[:\s]+(\d{7})',
        r'IMO[:\s]+(\d{7})',
    ], ["IMO Number", "IMO", "Vessel IMO"], text)

    barge_name = find([
        r'Barge\s+Name[:\s]+([A-Z0-9 ]+)',
        r'Bunker\s+Barge[:\s]+([A-Z0-9 ]+)',
        r'Bunker\s+Tanker[:\s]+([A-Z0-9 ]+)',
    ], ["Barge Name", "Bunker Barge", "Bunker Tanker", "Delivering Vessel", "SB Number"], text)

    barge_imo = None

    delivery_date = find([
        r'Delivery\s+Date[:\s]+(\d{1,2}\s+\w+\s+\d{4})',
        r'Date[:\s]+(\d{1,2}\s+\w+\s+\d{4})',
    ], ["Delivery Date", "Date", "Bunkering Date"], text)

    start_time = find([
        r'Pumping\s+Start\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
        r'Start\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
    ], ["Pumping Start Time", "Start Time", "Commenced Pumping", "Hose On"], text)

    end_time = find([
        r'Pumping\s+End\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
        r'End\s+Time[:\s]+(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})',
    ], ["Pumping End Time", "End Time", "Completed Pumping", "Hose Off"], text)

    port = find([
        r'Port\s+of\s+Delivery[:\s]+([A-Za-z ]+)',
        r'Port[:\s]+([A-Za-z ]+)',
    ], ["Port of Delivery", "Port", "Bunkering Port", "Location"], text)

    supplier = find([
        r'Supplier[:\s]+([A-Za-z ]+(?:Ltd|Inc|Pte|Corp)?)',
    ], ["Supplier", "Seller", "Bunker Company", "Physical Supplier"], text)

    quantity    = find_number([r'Quantity\s+Delivered[:\s]+([\d.,]+\s*MT)', r'Quantity[:\s]+([\d.,]+)'], ["Quantity Delivered", "Quantity", "Total Quantity", "Volume"], text)
    sulphur     = find_number([r'Sulphur\s+Content[:\s]+([\d.]+)', r'Sulphur[:\s]+([\d.]+)'], ["Sulphur Content", "Sulphur", "Sulfur"], text)

    # ── spaCy fallbacks ──────────────────────────────────────────────
    # Use spaCy only if regex failed
    if not port and spacy_entities.get("locations"):
        port = spacy_entities["locations"][0]

    if not supplier and spacy_entities.get("orgs"):
        supplier = spacy_entities["orgs"][0]

    if not delivery_date and spacy_entities.get("dates"):
        delivery_date = spacy_entities["dates"][0]

    return {
        "raw_text":         text,
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
        "sulphur_content":  sulphur,
        "ocr_confidence":   confidence,
        "spacy_entities":   spacy_entities   # kept for transparency
    }