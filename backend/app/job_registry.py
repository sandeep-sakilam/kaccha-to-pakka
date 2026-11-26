"""Import every module that defines jobs, so both the API and the worker know them."""

from app.modules.extraction import jobs as extraction_jobs  # noqa: F401
