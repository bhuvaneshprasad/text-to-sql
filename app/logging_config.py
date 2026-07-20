import logging
import sys

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure logging for the ``app`` logger namespace.

    Idempotent: safe to call from both the API startup and the bootstrap CLI.
    All module loggers created via ``logging.getLogger(__name__)`` live under
    ``app.*`` and propagate here, so a single handler covers the whole app.
    """
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger = logging.getLogger("app")
    logger.setLevel(level.upper())
    logger.handlers = [handler]
    logger.propagate = False

    _configured = True
