from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction


class Template(metaclass=PoolMeta):
    __name__ = 'product.template'

    supply_production_on_sale = fields.Boolean('Supply Production On Sale',
        states={
            'invisible': ~Eval('producible'),
            })

    @classmethod
    def __register__(cls, module_name):
        handler = cls.__table_handler__(module_name)
        existing = handler.column_exist('supply_production_on_sale')

        super().__register__(module_name)

        if not existing:
            Config = Pool().get('sale.configuration')
            config = Config(1)
            if config.sale_supply_production_default:
                table = cls.__table__()
                cursor = Transaction().connection.cursor()
                cursor.execute(*table.update(
                        columns=[table.supply_production_on_sale],
                        values=[True],
                        where=table.producible == True))



class Product(metaclass=PoolMeta):
    __name__ = 'product.product'

    def get_bom(self, pattern=None):
        return self.boms and self.boms[0]
