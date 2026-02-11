from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional
from dev_utils import get_topic_name


from common import load_kafka_payload
from flask import Flask, jsonify
from kafka_consumer import (KafkaConsumerSettings, consume_messages,
                            poll_messages, validate_user_data)
from kafka_producer import produce_message
from ollama import ModelNotRunningError, OllamaClient


@dataclass(frozen=True)
class ProcessorSettings:
    ollama_host: str
    ollama_model: Optional[str]
    kafka_topic: str
    expected_user_email: Optional[str]
    request_timeout: int
    health_timeout: int

    @classmethod
    def from_env(cls) -> "ProcessorSettings":
        import os

        return cls(
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL"),
            kafka_topic=os.getenv("LOCAL_MODEL_KAFKA_TOPIC", "eater-send-photo"),
            expected_user_email=os.getenv("EXPECTED_USER_EMAIL"),
            request_timeout=int(os.getenv("OLLAMA_REQUEST_TIMEOUT", "60")),
            health_timeout=int(os.getenv("OLLAMA_HEALTH_TIMEOUT", "5")),
        )


CODE_BLOCK_RE = re.compile(r"^```(?:[a-zA-Z0-9_+-]+)?\s*(.*?)\s*```$", re.DOTALL)


def _sanitize_analysis_result(result: Optional[str]) -> Optional[str]:
    if result is None:
        return None

    candidate = result.strip()
    match = CODE_BLOCK_RE.match(candidate)
    if match:
        candidate = match.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return candidate

    return json.dumps(parsed, ensure_ascii=False)


class ModelsProcessor:
    def __init__(
        self,
        settings: Optional[ProcessorSettings] = None,
        client_factory: Optional[Callable[[ProcessorSettings], OllamaClient]] = None,
    ) -> None:
        self.settings = settings or ProcessorSettings.from_env()
        self._client_factory = client_factory or self._default_client_factory
        self._client: Optional[OllamaClient] = None
        self._stop_event = threading.Event()
        self._consumer_thread: Optional[threading.Thread] = None
        self._consumer_settings = KafkaConsumerSettings.from_env()
        self.app = Flask(__name__)
        self._register_routes()

    @property
    def client(self) -> OllamaClient:
        if self._client is None:
            raise RuntimeError("Ollama client is not initialized. Call start() first.")
        return self._client

    def _default_client_factory(self, settings: ProcessorSettings) -> OllamaClient:
        return OllamaClient(
            host=settings.ollama_host,
            model=settings.ollama_model,
            request_timeout=settings.request_timeout,
            health_timeout=settings.health_timeout,
        )

    def start(self) -> None:
        if not self.settings.ollama_model:
            logging.error(
                "OLLAMA_MODEL environment variable must be set before starting"
            )
            raise SystemExit(1)

        if self._consumer_thread and self._consumer_thread.is_alive():
            logging.info("Consumer thread already running")
            return

        self._client = self._client_factory(self.settings)
        self._stop_event.clear()

        self._consumer_thread = threading.Thread(
            target=self._process_kafka_messages,
            name="kafka-consumer-thread",
            daemon=True,
        )
        self._consumer_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
        self._consumer_thread = None

    def _process_kafka_messages(self) -> None:
        topics = [get_topic_name(self.settings.kafka_topic)]
        logging.info("Starting Kafka message processing on topics: %s", topics)

        consumer = consume_messages(
            topics,
            settings=self._consumer_settings,
        )
        for message in poll_messages(consumer, stop_event=self._stop_event):
            if self._stop_event.is_set():
                logging.info("Stop flag set; exiting Kafka processing loop")
                break

            payload = load_kafka_payload(message.value())
            if payload is None:
                consumer.commit(message)
                continue

            logging.info(
                "Received message from topic '%s': %s", message.topic(), payload
            )

            if not isinstance(payload, dict):
                logging.warning(
                    "Unexpected payload type; expected dict but got %s", type(payload)
                )
                consumer.commit(message)
                continue

            if not validate_user_data(payload, self.settings.expected_user_email):
                logging.warning(
                    "Skipping message due to user validation failure: %s", payload
                )
                consumer.commit(message)
                continue

            value_dict = payload.get("value", {})
            prompt = value_dict.get("prompt")
            photo_base64 = value_dict.get("photo")
            user_email = value_dict.get("user_email")
            timestamp = value_dict.get("timestamp")
            date = value_dict.get("date")
            image_id = value_dict.get("image_id")

            has_photo = bool(photo_base64)
            target_topic = "photo-analysis-response"
            analysis_result: Optional[str]

            if has_photo:
                if not prompt:
                    logging.warning(
                        "Photo analysis message missing prompt; skipping processing: %s",
                        value_dict,
                    )
                    consumer.commit(message)
                    continue

                analysis_result = self.client.analyze_photo_with_ollama(
                    prompt, photo_base64
                )
            else:
                analysis_result = self.client.analyze_text_with_ollama(value_dict)
                target_topic = "gemini-response"

            analysis_result = _sanitize_analysis_result(analysis_result)

            if analysis_result is None:
                analysis_result = "Analysis failed; check service logs for details."

            key = message.key().decode("utf-8") if message.key() else None

            message_value: dict[str, Any] = {"user_email": user_email}

            if target_topic == "gemini-response":
                parsed_analysis: Any
                try:
                    parsed_analysis = json.loads(analysis_result)
                except json.JSONDecodeError:
                    message_value["analysis"] = analysis_result
                else:
                    if isinstance(parsed_analysis, dict):
                        message_value.update(parsed_analysis)
                    else:
                        message_value["analysis"] = analysis_result
            else:
                message_value["analysis"] = analysis_result
            
            if timestamp:
                message_value["timestamp"] = timestamp
            if date:
                message_value["date"] = date
            if image_id:
                message_value["image_id"] = image_id

            kafka_message = {
                "key": key,
                "value": message_value,
            }

            try:
                produce_message(target_topic, kafka_message)
                logging.info(
                    "Produced analysis result to '%s': %s",
                    target_topic,
                    kafka_message,
                )
            except Exception as exc:  # Catch-all to avoid crashing the consumer loop
                logging.error("Failed to produce analysis message: %s", exc)

            consumer.commit(message)

    def _register_routes(self) -> None:
        self.app.add_url_rule("/health", "health", self.health_check, methods=["GET"])
        self.app.add_url_rule("/ready", "ready", self.readiness_check, methods=["GET"])

    def health_check(self):  # type: ignore[override]
        if self._client is None:
            logging.error("Health check requested before Ollama client initialized")
            return (
                jsonify({"status": "unhealthy", "detail": "Service not initialized"}),
                503,
            )

        try:
            self.client.assert_model_running()
            return (
                jsonify(
                    {
                        "status": "ok",
                        "model": self.client.model,
                    }
                ),
                200,
            )
        except ModelNotRunningError as exc:
            logging.warning("Health check failed: %s", exc)
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "detail": str(exc),
                    }
                ),
                503,
            )

    def readiness_check(self):  # type: ignore[override]
        if self._client is None:
            logging.warning("Readiness probe failed: Ollama client not yet initialised")
            return (
                jsonify(
                    {
                        "status": "not_ready",
                        "detail": "Ollama client not initialised",
                    }
                ),
                503,
            )

        if not (self._consumer_thread and self._consumer_thread.is_alive()):
            logging.warning("Readiness probe failed: consumer thread is not running")
            return (
                jsonify(
                    {
                        "status": "not_ready",
                        "detail": "Kafka consumer thread not running",
                    }
                ),
                503,
            )

        return (
            jsonify(
                {
                    "status": "ready",
                    "topic": self.settings.kafka_topic,
                }
            ),
            200,
        )


__all__ = ["ModelsProcessor", "ProcessorSettings"]
