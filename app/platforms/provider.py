from abc import ABC, abstractmethod
from typing import Optional

from app.models.product import Product


class ProductProvider(ABC):

    @abstractmethod
    def get_product(self, url: str) -> Optional[Product]:
        """
        Obtém os dados de um produto a partir de uma URL.

        Retorna Product quando conseguir obter os dados.
        Retorna None quando o produto não puder ser obtido.
        """
        raise NotImplementedError
