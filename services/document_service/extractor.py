import re
from services.document_service.ocr import extract_text_with_confidence

def extract_fields(file_path: str) -> dict:
    """
    Extract all required BDN fields from image using regex.
    Returns structured dict with extracted values and confidence.
    """
    result = extract_text_with_confidence(file_path)
    text = result["text"]
    confidence = result["confidence"]

    def find(patterns, text):
        """Try multiple regex patterns, return first match or None."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

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

    # Numeric fields — clean symbols before parsing
    def find_number(patterns, text):
        val = find(patterns, text)
        if val:
            # Remove units and symbols, keep digits and decimal point
            cleaned = re.sub(r'[^\d.]', '', val.split()[0])
            try:
                return float(cleaned)
            except:
                return None
        return None

    quantity = find_number([
        r'Quantity\s+Delivered[:\s]+([\d.,]+\s*MT)',
        r'Quantity[:\s]+([\d.,]+)',
    ], text)

    density = find_number([
        r'Density[^:]*[:\s]+([\d.]+)\s*kg',
        r'Density[^:]*[:\s]+([\d.]+)',
    ], text)

    sulphur = find_number([
        r'Sulphur\s+Content[:\s]+([\d.]+)',
        r'Sulphur[:\s]+([\d.]+)',
    ], text)

    flashpoint = find_number([
        r'Flashpoint[:\s]+([\d.]+)',
        r'Flash\s+Point[:\s]+([\d.]+)',
    ], text)

    return {
        "vessel_name":    vessel_name,
        "imo":            imo,
        "barge_name":     barge_name,
        "barge_imo":      barge_imo,
        "delivery_date":  delivery_date,
        "start_time":     start_time,
        "end_time":       end_time,
        "port":           port,
        "supplier":       supplier,
        "quantity_mt":    quantity,
        "density":        density,
        "sulphur_content":sulphur,
        "flashpoint":     flashpoint,
        "ocr_confidence": confidence
    }