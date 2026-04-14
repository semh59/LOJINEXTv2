import abc
import asyncio
import json
import logging
from typing import Any

try:
    from platform_common.context import causation_id, correlation_id  # type: ignore
except ImportError:
    from .context import causation_id, correlation_id  # type: ignore

logger = logging.getLogger(__name__)

try:
    from confluent_kafka import Consumer as ConfluentConsumer  # type: ignore
    from confluent_kafka import Message  # type: ignore
except ImportError:
    ConfluentConsumer = None
    Message = Any

class KafkaConsumerBase(abc.ABC):
    """Abstract base class for standardizing message consumption."""

    def __init__(
        self,
        config: dict[str, Any],
        topics: list[str],
        *,
        poll_timeout: float = 1.0,
    ) -> None:
        if ConfluentConsumer is None:
            raise RuntimeError("confluent-kafka is not installed.")
        config.setdefault("enable.auto.commit", False)
        config.setdefault("auto.offset.reset", "earliest")
        self.consumer = ConfluentConsumer(config)
        self._enable_auto_commit = config.get("enable.auto.commit", False)
        self.topics = topics
        self.poll_timeout = poll_timeout
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self.consumer.subscribe(self.topics)
        self._running = True
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._consume_loop())
        logger.info("Kafka consumer started: %s", self.topics)

    async def stop(self) -> None:
        self._running = False
        task = self._task
        if task:
            try:
                await asyncio.wait_for(task, timeout=10.0)
            except asyncio.TimeoutError:
                task.cancel()
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.consumer.close)
        logger.info("Kafka consumer stopped.")

    async def _consume_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                msg = await loop.run_in_executor(None, self.consumer.poll, self.poll_timeout)
            except Exception as e:
                logger.error("Poll error: %s", str(e))
                await asyncio.sleep(1.0)
                continue
            if msg is None:
                continue

            # ELITE HARDENING: Narrow to Msg object specifically for type checks
            message = msg
            if message is not None and hasattr(message, "error") and callable(message.error):
                err = message.error()
                if err:
                    if err.code() == -191:  # _PARTITION_EOF
                        continue
                    logger.error("Consumer error: %s", err)
                    continue

            try:
                await self._process_message(message)
                if not self._enable_auto_commit:
                    await loop.run_in_executor(None, self.consumer.commit, message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Process error: %s", str(e))

    async def _process_message(self, msg: Message) -> None:
        try:
            val_bytes = msg.value()
            if not val_bytes:
                return
            payload = json.loads(val_bytes.decode("utf-8"))
        except Exception:
            logger.error("Decode error")
            return
        
        headers_dict: dict[str, str] = {}
        msg_headers = msg.headers()
        if msg_headers:
            for header in msg_headers:
                if isinstance(header, tuple) and len(header) >= 2:
                    k, v = header[0], header[1]
                    if v is not None:
                        if isinstance(v, bytes):
                            headers_dict[str(k)] = v.decode("utf-8")
                        else:
                            headers_dict[str(k)] = str(v)

        correlation_id_val = headers_dict.get("X-Correlation-ID")
        causation_id_val = payload.get("event_id") or payload.get("id") or correlation_id_val
        
        cor_token = correlation_id.set(correlation_id_val)
        cau_token = causation_id.set(causation_id_val)

        try:
            await self.process(
                topic=msg.topic(),
                key=msg.key().decode("utf-8") if msg.key() else None,
                payload=payload,
                correlation_id=correlation_id_val,
                causation_id=causation_id_val,
            )
        finally:
            correlation_id.reset(cor_token)
            causation_id.reset(cau_token)

    @abc.abstractmethod
    async def process(
        self,
        topic: str,
        key: str | None,
        payload: dict[str, Any],
        correlation_id: str | None,
        causation_id: str | None,
    ) -> None:
        ...
