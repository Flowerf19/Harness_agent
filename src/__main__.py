# Entry point để chạy bot với: python3 -m src
import warnings

from src.bot import main

warnings.warn(
    "⚠️ Standalone mode is deprecated. Use 'python3 -m gateway' instead.",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    main()
