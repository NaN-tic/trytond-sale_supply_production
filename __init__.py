#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.pool import Pool
from . import configuration
from . import production
from . import sale


def register():
    Pool.register(
        configuration.Configuration,
        production.Production,
        production.ChangeQuantityStart,
        sale.Sale,
        sale.SaleLine,
        module='sale_supply_production', type_='model')
    Pool.register(
        production.ChangeQuantity,
        depends=['sale_change_quantity'],
        module='sale_supply_production', type_='wizard')
    Pool.register(
        sale.ChangeLineQuantity,
        depends=['sale_change_quantity'],
        module='sale_supply_production', type_='wizard')
