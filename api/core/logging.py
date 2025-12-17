import logging
import os


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Set up a logger with the specified name and level."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Create console handler and set level
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Add formatter to ch
    ch.setFormatter(formatter)

    # Add ch to logger
    logger.addHandler(ch)

    # Ensure logs directory exists before creating file handler
    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("./logs/app.log")
    fh.setLevel(level)

    # Add formatter to fh
    fh.setFormatter(formatter)

    # Add fh to logger
    logger.addHandler(fh)

    return logger


# Example of setting up a logger
logger = get_logger(__name__)
