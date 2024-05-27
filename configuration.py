from trytond.model import fields
from trytond.pool import PoolMeta


class Configuration(metaclass=PoolMeta):
    __name__ = 'sale.configuration'
    sale_supply_production_default = fields.Boolean(
        'Sale Line Supply Production',
        help='Default Supply Production value for Sale Lines')

    @staticmethod
    def default_sale_supply_production_default():
        return True
