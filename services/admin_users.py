"""Cloud user management is unavailable in the single-owner local edition."""


def _disabled(*args, **kwargs):
    raise RuntimeError("User management is disabled in local mode")
