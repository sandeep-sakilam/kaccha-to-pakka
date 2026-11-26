from sqlalchemy.orm import Session

from app.jobs import job
from app.modules.review.service import monitor


@job("sahayak_monitor")
def monitor_job(db: Session) -> None:
    monitor(db)
