#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Product', 'Sale', 'SaleLine']
__metaclass__ = PoolMeta


class Product:
    __name__ = 'product.product'

    @classmethod
    def get_sale_price(cls, products, quantity=0):
        CostPlan = Pool().get('product.cost.plan')
        res = super(Product, cls).get_sale_price(products, quantity)
        cost_plan = Transaction().context.get('cost_plan')
        if cost_plan:
            unit_price = CostPlan(cost_plan).unit_price
            for x in res.keys():
                res[x] = unit_price
        return res


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
        domain=[
            ('party', '=', Eval('_parent_sale', {}).get('party')),
            ('product', '=', Eval('product', 0)),
            ('state', '=', 'computed'),
            ],
        depends=['type', 'product', '_parent_sale.party'], states={
            'invisible': Eval('type') != 'line',
            }, on_change=['cost_plan'])
    productions = fields.One2Many('production', 'origin', 'Productions')

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        if 'cost_plan' not in cls.amount.on_change_with:
            cls.amount.on_change_with.append('cost_plan')
        if 'cost_plan' not in cls.quantity.on_change:
            cls.quantity.on_change.append('cost_plan')
        for field in cls.quantity.on_change:
            if field not in cls.cost_plan.on_change:
                cls.cost_plan.on_change.append(field)

    def on_change_cost_plan(self):
        return self.on_change_quantity()

    def _get_context_sale_price(self):
        context = super(SaleLine, self)._get_context_sale_price()
        if hasattr(self, 'cost_plan'):
            context['cost_plan'] = self.cost_plan.id if self.cost_plan else None
        return context

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
