"""Delivery channel abstraction for Research Radar."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ....models.schemas import PushDigest


class DeliveryChannel(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this channel can be used in the current environment."""
        ...

    @abstractmethod
    def deliver(self, anon_user_id: str, digest: PushDigest) -> bool:
        """Deliver one digest. Raise on operational failure."""
        ...
