"""Logging setup for Timecoder."""

import logging
import logging.config
from pathlib import Path

import yaml


def setup_logging(config_path: str | None = None) -> None:
    """Configure logging from YAML file.

    Args:
        config_path: Path to logging_config.yaml. Uses default if None.
    """
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent.parent / "config" / "logging_config.yaml"
        )

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Ensure log directory exists
        for handler in config.get("handlers", {}).values():
            if "filename" in handler:
                Path(handler["filename"]).parent.mkdir(parents=True, exist_ok=True)

        logging.config.dictConfig(config)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)
