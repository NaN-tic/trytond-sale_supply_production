#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from .production import *
from .sale import *


def register():
    Pool.register(
        Product,
        Production,
        Plan,
        PlanBOM,
        SaleLine,
        Sale,
        module='sale_cost_plan', type_='model')
