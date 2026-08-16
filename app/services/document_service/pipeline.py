from app.services.document_service.classifier import classify_document
from app.services.document_service.extractor import extract_fields
from app.services.document_service.credibility import check_credibility


def process_bdn(file_path: str) -> dict:
    """
    Full document processing pipeline.
    Step 1 — Classify document type
    Step 2 — Extract all fields
    Step 3 — Run credibility checks
    Returns combined result dict.
    """
    from app.services.document_service.pdf_utils import document_image_source

    with document_image_source(file_path) as image_path:
        working = str(image_path)
        classification = classify_document(working)
        fields = extract_fields(working)
        fields["doc_type"] = classification["doc_type"]
        fields["font_variance"] = classification.get("font_variance")
        fields["ocr_confidence"] = fields.get("ocr_confidence") or classification.get("ocr_confidence")
        credibility = check_credibility(fields)

        return {
            "file": file_path,
            "rasterized": working if working != file_path else None,
            "classification": classification,
            "extraction": fields,
            "credibility": credibility,
        }
