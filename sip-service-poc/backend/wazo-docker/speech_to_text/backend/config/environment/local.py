import os

from dotenv import load_dotenv

env_variables = {
    "APP_MODE": "LOCAL",
    "APP_CONTAINERIZED": "false",
    "APP_LOG_LEVEL": "DEBUG",
    "APP_LOG_PATH": "logs",
    "APP_TOKEN": "changeme",
}


def apply_local_env():
    load_dotenv()

    for var_key, var_val in env_variables.items():
        if os.getenv(var_key) is None:
            os.environ[var_key] = str(var_val)
