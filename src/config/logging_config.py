import logging


def setup_logging():
    """
    Setup logging configuration with third-party library suppression.

    Suppresses verbose INFO logs from:
    - discord.client, discord.gateway (Discord library connection logs)
    - qdrant_client (Vector DB client logs)
    - redis (Redis client logs)
    - httpx (HTTP client logs)
    - sentence_transformers (Embedding model logs)
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    # Suppress third-party library INFO logs (downgrade to WARNING)
    third_party_loggers = [
        "discord.client",
        "discord.gateway",
        "qdrant_client",
        "redis",
        "httpx",
        "sentence_transformers",
    ]

    for lib_logger in third_party_loggers:
        logging.getLogger(lib_logger).setLevel(logging.WARNING)

    logger = logging.getLogger('discord_bot')
    return logger


logger = setup_logging()