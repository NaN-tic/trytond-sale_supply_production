#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .production import *
from .sale import *


def register():
    Pool.register(
        Production,
        ChangeQuantityStart,
        SaleLine,
        Sale,
        ChangeLineQuantityStart,
        module='sale_supply_production', type_='model')
    Pool.register(
        ChangeQuantity,
        ChangeLineQuantity,
        module='sale_supply_production', type_='wizard')
