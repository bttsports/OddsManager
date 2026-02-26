"""
OddsManager market making bot. Run with: python -m market_making.bot
Reads config from market_making/config.json by default.
"""
from .bot import run

__all__ = ["run"]
