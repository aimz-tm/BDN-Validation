import json
from services.validation_service.orchestrator import run_validation

def main():
    try:
        verdict = run_validation("d:/129Knots/clone/BDN-Validation/test_bdn.png")
        print("Verdict Status:", verdict.get("classification"))
        print("Confidence:", verdict.get("confidence"))
        print("Reason:", verdict.get("verdict_reason"))
        print("\nAIS Flags:", verdict.get("anomaly_flags"))
        print("Identity Resolved:", not verdict.get("identity_resolution", {}).get("vessel_identity_unresolved"))
    except Exception as e:
        print("Error:", str(e))

if __name__ == "__main__":
    main()
