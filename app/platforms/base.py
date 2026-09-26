from abc import ABC, abstractmethod
from app.models.product import Product


class PlatformAdapter(ABC):

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        pass

    @abstractmethod
    def fetch_product(self, url: str) -> Product:
        pass
