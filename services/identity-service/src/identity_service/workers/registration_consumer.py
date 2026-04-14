"""Consumer for user registration events to synchronize profiles."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from platform_common.consumer import KafkaConsumerBase

from identity_service.config import settings
from identity_service.database import async_session_factory
from identity_service.models import IdentityUserModel

logger = logging.getLogger("identity_service.registration_consumer")

class RegistrationConsumer(KafkaConsumerBase):
    """Consumer that listens for user registration events and creates profiles."""

    def __init__(self) -> None:
        config = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "identity-registration-consumer",
            "auto.offset.reset": "earliest",
        }
        # auth-service outputs to its own topic (usually identity.events.v1 by default in settings)
        # We subscribe to that.
        super().__init__(config, [settings.kafka_topic])

    async def process(
        self,
        topic: str,
        key: str | None,
        payload: dict[str, Any],
        correlation_id: str | None,
        causation_id: str | None,
    ) -> None:
        """Process a single event from Kafka."""
        event_type = payload.get("event_type")
        
        # Standard outbox-relay payload has: aggregate_id, aggregate_type, event_type, payload
        if event_type == "user.registered":
            data = payload.get("payload")
            # If the relay keeps it as a JSON string, parse it.
            if isinstance(data, str):
                import json
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse nested payload: %s", data)
                    return
            
            await self._create_profile(data)
        else:
            logger.debug("Skipping unrelated event: %s", event_type)

    async def _create_profile(self, data: dict) -> None:
        """Create a user profile row in identity_users."""
        user_id = data.get("user_id")
        email = data.get("email")
        
        if not user_id or not email:
            logger.warning("Invalid registration payload: missing user_id or email")
            return

        async with async_session_factory() as session:
            try:
                # Check if profile already exists (Idempotency)
                existing = await session.get(IdentityUserModel, user_id)
                if existing:
                    logger.info("Profile already exists for user_id: %s", user_id)
                    return

                # Create profile
                username = email.split("@")[0] if "@" in email else user_id
                
                new_user = IdentityUserModel(
                    user_id=user_id,
                    username=username,
                    email=email,
                    is_active=True,
                    created_at_utc=datetime.now(UTC),
                    updated_at_utc=datetime.now(UTC)
                )
                session.add(new_user)
                await session.commit()
                logger.info("Successfully created identity profile for user: %s (ID: %s)", email, user_id)

            except Exception as exc:
                await session.rollback()
                logger.error("Database error while creating profile for %s: %s", email, str(exc))
                raise

def main() -> None:
    """Entry point for the registration consumer worker."""
    logging.basicConfig(level=logging.INFO)
    consumer = RegistrationConsumer()
    
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(consumer.start())
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(consumer.stop())
    finally:
        loop.close()

if __name__ == "__main__":
    main()
