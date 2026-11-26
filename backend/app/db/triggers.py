"""Database-level guarantees that must hold even if application code is wrong."""

from sqlalchemy import DDL, event

from app.db.models import Assessment, AuditLog

AUDIT_APPEND_ONLY = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
"""

_ddl = DDL(AUDIT_APPEND_ONLY)  # type: ignore[no-untyped-call]
event.listen(AuditLog.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))

ASSESSMENT_IMMUTABLE = """
CREATE OR REPLACE FUNCTION assessments_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'assessments are immutable; create a new one';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS assessments_no_change ON assessments;
CREATE TRIGGER assessments_no_change BEFORE UPDATE OR DELETE ON assessments
  FOR EACH ROW EXECUTE FUNCTION assessments_immutable();
"""

_ddl2 = DDL(ASSESSMENT_IMMUTABLE)  # type: ignore[no-untyped-call]
event.listen(Assessment.__table__, "after_create", _ddl2.execute_if(dialect="postgresql"))
