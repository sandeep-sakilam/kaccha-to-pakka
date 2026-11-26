from sqlalchemy.orm import Session

from app.jobs import job
from app.modules.extraction.service import extract_evidence


@job("extract_ledger")
def extract_ledger_job(db: Session, evidence_id: str) -> None:
    extract_evidence(db, evidence_id)
