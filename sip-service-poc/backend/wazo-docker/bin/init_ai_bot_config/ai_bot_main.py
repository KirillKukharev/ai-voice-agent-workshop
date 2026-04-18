import asyncio
import logging

from ai_bot_service import AIBotService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main function"""
    service = AIBotService()

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal")
    except Exception as e:
        logger.error(f"❌ Service error: {e}")
        return 1
    finally:
        await service.stop()

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
