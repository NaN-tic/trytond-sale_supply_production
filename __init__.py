#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .production import *
from .sale import *


def register():
    Pool.register(
        Production,
        Plan,
        PlanBOM,
        SaleLine,
        Sale,
        ChangeLineQuantityStart,
        module='sale_cost_plan', type_='model')
    Pool.register(
        ChangeLineQuantity,
        module='sale_cost_plan', type_='wizard')
