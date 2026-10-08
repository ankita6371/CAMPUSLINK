import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("CAMPUSLINK_SECRET_KEY") or secrets.token_hex(32)

    DATABASE = os.path.join(
        BASE_DIR,
        "instance",
        "campuslink.db"
    )

    APP_NAME = "CAMPUSLINK"
    APP_VERSION = "1.0.0"