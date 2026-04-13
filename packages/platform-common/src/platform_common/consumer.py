"""Generic Kafka Consumer Base for standardizing event consumption across LOJINEXT services."""

import abc
import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from confluent_kafka import Consumer as ConfluentConsumer
    from confluent_kafka import Message
except ImportError:
    ConfluentConsumer = None
    Message = Any

class KafkaConsumerBase(abc.ABC):
    """Abstract base class for standardizing message consumption.

    Provides built-in handling for:
      - X-Correlation-ID and X-Causation-ID extraction
      - Graceful shutdown and cancellation hooks
      - Basic deserialization and continuous polling
    """

    def __init__(
        self,
        config: dict[str, Any],
        topics: list[str],
        *,
        poll_timeout: float = 1.0,
    ) -> None:
        """Initialize the Kafka consumer base.

        Args:
            config: A confluent-kafka consumer configuration dictionary.
            topics: A list of topics to subscribe to.
            poll_timeout: How long to wait on each poll() cycle.
        """
        if ConfluentConsumer is None:
            raise RuntimeError("confluent-kafka is not installed.")

        # Ensure essential production configuration defaults
        config.setdefault("enable.auto.commit", False)
        config.setdefault("auto.offset.reset", "earliest")

        self.consumer = ConfluentConsumer(config)
        self.topics = topics
        self.poll_timeout = poll_timeout
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Subscribe and start the consumption loop in a background task."""
        if self._running:
            return

        self.consumer.subscribe(self.topics)
        self._running = True
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._consume_loop())

        logger.info("Kafka consumer started and subscribed to topics: %s", self.topics)

    async def stop(self) -> None:
        """Signal the consumer to stop and perform a clean shutdown."""
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Kafka consumer did not terminate gracefully within 10s.")
                self._task.cancel()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.consumer.close)
        logger.info("Kafka consumer stopped gracefully.")

    async def _consume_loop(self) -> None:
        """Main loop that continuously polls for Kafka messages."""
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                # Use executor to avoid blocking the event loop on I/O
                # We do this instead of looping entirely off-thread to integrate cleanly with async apps.
                msg = await loop.run_in_executor(None, self.consumer.poll, self.poll_timeout)
            except Exception as e:
                logger.error("Error during Kafka poll: %s", str(e), exc_info=True)
                await asyncio.sleep(1.0)  # Backoff on connection error
                continue

            if msg is None:
                continue

            if msg.error():
                # End of partition is not a real error
                if msg.error().code() == -191:  # PARTITION_EOF
                    continue
                logger.error("Kafka consumer error: %s", msg.error())
                continue

            # Process the message
            try:
                await self._process_message(msg)
                if not self.consumer.config().get('enable.auto.commit'):
                    # Manually commit the offset internally
                    await loop.run_in_executor(None, self.consumer.commit, msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Unhandled error processing message %s: %s", msg.key(), str(e), exc_info=True)

    async def _process_message(self, msg: Message) -> None:
        """A internal wrapper to deserialize payload and extract trace IDs."""
        try:
            val_bytes = msg.value()
            if not val_bytes:
                return
            
            payload = json.loads(val_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.error("Failed to decode message on topic %s", msg.topic())
            return
        
        headers_dict: dict[str, str] = {}
        if msg.headers():
            for key, val in msg.headers():
                if val:
                    headers_dict[key] = val.decode("utf-8")

        correlation_id = headers_dict.get("X-Correlation-ID")
        causation_id = headers_dict.get("X-Causation-ID")
        
        # Now dispatch to subclass
        await self.process(
            topic=msg.topic(),
            key=msg.key().decode("utf-8") if msg.key() else None,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    @abc.abstractmethod
    async def process(
        self,
        topic: str,
        key: str | None,
        payload: dict[str, Any],
        correlation_id: str | None,
        causation_id: str | None,
    ) -> None:
        """Override this method to implement service-specific logic for processing events.
        
        Args:
            topic: The topic the message arrived on.
            key: The Kafka partition key (typically the aggregate ID).
            payload: The deserialized JSON payload dictionary.
            correlation_id: Trace string extracted from X-Correlation-ID header.
            causation_id: Trace string extracted from X-Causation-ID header.
        """
        ...
