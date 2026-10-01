"""Market intelligence and evidence analysis.

External events are cold-path, PIT-safe evidence. They are not directional votes.
"""

from .events import EventCategory, EventImpact, ExternalEvent, ExternalEventEngine, ExternalEventSnapshot
from .external import ExternalEventIngestion, ExternalEventNormalizer, ExternalEventProvider, RawExternalEvent

__all__ = [
    "EventCategory",
    "EventImpact",
    "ExternalEvent",
    "ExternalEventEngine",
    "ExternalEventSnapshot",
    "ExternalEventIngestion",
    "ExternalEventNormalizer",
    "ExternalEventProvider",
    "RawExternalEvent",
]
