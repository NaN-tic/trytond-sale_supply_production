#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Sale', 'SaleLine']
__metaclass__ = PoolMeta


class Sale:
    __name__ = 'sale.sale'

    productions = fields.Function(fields.One2Many('production', None,
        'Productions'), 'get_productions')

    @classmethod
    def process(cls, sales):
        for sale in sales:
            if sale.state in ('done', 'cancel'):
                continue
            with Transaction().set_user(0, set_context=True):
                sale.create_productions()
        super(Sale, cls).process(sales)

    def create_productions(self):
        for line in self.lines:
            productions = line.get_productions()
            for production in productions:
                production.cost_plan = line.cost_plan
                production.origin = str(line)
                production.reference = self.reference
                production.save()

    def get_productions(self, name):
        productions = []
        for line in self.lines:
            productions.extend([p.id for p in line.productions])
        return productions


class SaleLine:
    __name__ = 'sale.line'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        domain=[('product', '=', Eval('product', 0)),
            ('state', '=', 'computed')],
        depends=['type', 'product'], states={
            'invisible': Eval('type') != 'line',
            }, on_change=['cost_plan'])
    productions = fields.One2Many('production', 'origin', 'Productions')

    def on_change_cost_plan(self):
        if self.cost_plan:
            if hasattr(self.cost_plan, 'unit_price'):
                return {'unit_price': self.cost_plan.unit_price}
        return {}

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['productions'] = None
        return super(SaleLine, cls).copy(lines, default=default)

    def get_productions(self):
        if not self.cost_plan:
            return []
        if len(self.productions) > 0:
            return []
        return self.cost_plan.get_productions(self.sale.warehouse, self.unit,
            self.quantity)
