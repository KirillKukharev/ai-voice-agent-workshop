import logging
import os
from pathlib import Path

import colorlog

from backend.core.constants import ApplicationMode, LogColor


def configure_application():
    """Apply config"""
    # Load env from files once (safe if module absent)
    try:
        from env_loader import load_environment_once

        load_environment_once()
    except Exception:
        pass

    def show_debug_message():
        """Prints debug message"""
        logger = logging.getLogger(__name__)
        logger.debug(
            "\n######################################\n"
            "#              WARNING!              #\n"
            "#    App is running in DEV mode      #\n"
            "#   DO NOT USE IT IN PRODUCTION!     #\n"
            "######################################\n"
        )

    def configure_logging():
        """Base logger config"""
        root_logger = logging.getLogger()

        # If logger exists
        if root_logger.handlers:
            return

        log_level = os.getenv("APP_LOG_LEVEL", "INFO")
        root_logger.setLevel(log_level)

        standard_formatter = logging.Formatter(
            fmt="[%(asctime)s] - %(levelname)s - %(process)d - %(name)s:%(lineno)d: %(message)s",
            datefmt="%d.%m.%Y %H:%M:%S",
        )

        colored_formatter = colorlog.ColoredFormatter(
            fmt="%(log_color)s[%(asctime)s] - %(levelname)s - %(process)d - %(name)s:%(lineno)d:%(reset)s %(message)s",
            datefmt="%d.%m.%Y %H:%M:%S",
            log_colors={
                "DEBUG": LogColor.DEBUG,
                "INFO": LogColor.INFO,
                "WARNING": LogColor.WARNING,
                "ERROR": LogColor.ERROR,
                "CRITICAL": LogColor.CRITICAL,
            },
            secondary_log_colors={},
            style="%",
        )

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(colored_formatter)
        root_logger.addHandler(stream_handler)

        containerized = os.getenv("APP_CONTAINERIZED", "false").lower() == "true"
        if not containerized and (log_path := os.getenv("APP_LOG_PATH")):
            if Path(log_path).is_file():
                log_dir = Path(log_path).parent
                log_file = log_path
            else:
                log_dir = log_path
                log_file = Path(log_dir).join("app.log")

            Path(log_dir).mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(filename=log_file, encoding="utf-8")
            file_handler.setLevel(log_level)
            file_handler.setFormatter(standard_formatter)
            root_logger.addHandler(file_handler)

        logging.getLogger("openai").setLevel(os.getenv("APP_OPENAI_LOG_LEVEL", "WARNING"))
        logging.getLogger("httpcore").setLevel(os.getenv("APP_HTTPCORE_LOG_LEVEL", "WARNING"))
        logging.getLogger("httpx").setLevel(os.getenv("APP_HTTPX_LOG_LEVEL", "WARNING"))

    app_mode = ApplicationMode(os.getenv("APP_MODE", str(ApplicationMode.LOCAL)))

    if app_mode in (ApplicationMode.LOCAL, ApplicationMode.DEV):
        show_debug_message()

    if app_mode == ApplicationMode.LOCAL:
        from backend.config.environment.local import (  # pylint: disable=C0415
            apply_local_env,
        )

        apply_local_env()

    configure_logging()
