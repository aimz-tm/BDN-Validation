from services.document_service.classifier import classify_document
from services.document_service.extractor import extract_fields
from services.document_service.credibility import check_credibility


def process_bdn(file_path: str) -> dict:
    """
    Full document processing pipeline.
    Step 1 — Classify document type
    Step 2 — Extract all fields
    Step 3 — Run credibility checks
    Returns combined result dict.
    """
    # Step 1 — Classification
    classification = classify_document(file_path)

    # Step 2 — Field extraction
    fields = extract_fields(file_path)
    fields["doc_type"] = classification["doc_type"]

    # Step 3 — Credibility
    credibility = check_credibility(fields)

    return {
        "file": file_path,
        "classification": classification,
        "extraction": fields,
        "credibility": credibility
    }