import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Android Automated Trading Management Bot"
    VERSION: str = "1.0.0"
    
    # Database URL (SQLite for local dev, PostgreSQL for production VPS)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./trading_bot.db")
    
    # Binance API Configuration (Testnet / Live)
    BINANCE_USE_TESTNET: bool = os.getenv("BINANCE_USE_TESTNET", "True").lower() == "true"
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    
    # Trading Defaults
    DEFAULT_INITIAL_MARGIN: float = 2.0
    DEFAULT_AVERAGING_MARGIN: float = 2.0
    DEFAULT_OPPOSITE_MARGIN: float = 2.0
    DEFAULT_LEVERAGE: int = 6
    DEFAULT_TP_PERCENT: float = 3.0
    DEFAULT_SL_PERCENT: float = 12.0
    DEFAULT_WARNING_PERCENT: float = 6.0
    DEFAULT_OPPOSITE_PERCENT: float = 7.0
    DEFAULT_AVERAGING_PERCENT: float = 9.0
    DEFAULT_REENTRY_PERCENT: float = 1.0

settings = Settings()
