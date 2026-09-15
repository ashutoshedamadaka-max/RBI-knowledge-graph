"""Small, transparent guardrail for the RBI lending-only knowledge base."""

LENDING_TERMS = (
    "advance", "asset classification", "bank", "borrower", "co-lend", "colend",
    "collateral", "credit", "default", "digital lending", "emi", "interest",
    "kfs", "lend", "loan", "mortgage", "nbfc", "penal", "property document",
    "provision", "repayment", "settlement",
)


def is_rbi_lending_question(query: str) -> bool:
    normalized = query.lower()
    return any(term in normalized for term in LENDING_TERMS)
