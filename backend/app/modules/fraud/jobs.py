from sqlalchemy.orm import Session

from app.jobs import job
from app.modules.fraud.graph import scan


@job("fraud_graph_scan")
def scan_job(db: Session) -> None:
    scan(db)
