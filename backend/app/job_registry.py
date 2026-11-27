"""Import every module that defines jobs, so both the API and the worker know them."""

from app.modules.aa import service as aa_jobs  # noqa: F401
from app.modules.extraction import jobs as extraction_jobs  # noqa: F401
from app.modules.fraud import jobs as fraud_jobs  # noqa: F401
from app.modules.ops import metrics as ops_jobs  # noqa: F401
from app.modules.presence import service as presence_jobs  # noqa: F401
from app.modules.review import jobs as review_jobs  # noqa: F401
