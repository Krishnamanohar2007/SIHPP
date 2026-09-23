"""Replaceable notification transports."""
from abc import ABC, abstractmethod
import logging
from typing import Any, Mapping


logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    name: str

    @abstractmethod
    def send(self, recipient: str, message: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        """Send one message or raise an exception when delivery fails."""


class ConsoleChannel(NotificationChannel):
    name = "console"

    def send(self, recipient: str, message: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        logger.warning("notification console recipient=%s message=%s metadata=%s", recipient, message, dict(metadata))
        return {"delivery": "logged"}


class StubSMSChannel(NotificationChannel):
    name = "sms"

    def send(self, recipient: str, message: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        logger.info("would send via SMS recipient=%s message=%s metadata=%s", recipient, message, dict(metadata))
        return {"delivery": "stubbed"}


class StubEmailChannel(NotificationChannel):
    name = "email"

    def send(self, recipient: str, message: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        logger.info("would send via email recipient=%s message=%s metadata=%s", recipient, message, dict(metadata))
        return {"delivery": "stubbed"}


class StubPushChannel(NotificationChannel):
    name = "push"

    def send(self, recipient: str, message: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        logger.info("would send via push recipient=%s message=%s metadata=%s", recipient, message, dict(metadata))
        return {"delivery": "stubbed"}


CHANNEL_TYPES = {channel.name: channel for channel in (ConsoleChannel, StubSMSChannel, StubEmailChannel, StubPushChannel)}
