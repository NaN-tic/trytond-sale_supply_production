from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval


class Template(metaclass=PoolMeta):
    __name__ = 'product.template'

    supply_production_on_sale = fields.Boolean('Supply Production On Sale',
        states={
            'invisible': ~Eval('producible'),
            })


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'
