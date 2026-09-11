import logging
from abc import ABC, abstractmethod

from app.models.monitoring import RegulatoryUpdate

logger = logging.getLogger(__name__)


class RegulatoryAlertSender(ABC):
    @abstractmethod
    def send_regulatory_alert(self, update: RegulatoryUpdate) -> None:
        raise NotImplementedError


class LogAlertSender(RegulatoryAlertSender):
    def send_regulatory_alert(self, update: RegulatoryUpdate) -> None:
        logger.info("regulatory_update_alert update_id=%s materiality=%s", update.update_id, update.materiality.value)

