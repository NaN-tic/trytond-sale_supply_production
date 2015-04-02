# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Sale', 'SaleLine']
__metaclass__ = PoolMeta


class Sale:
    __name__ = 'sale.sale'
    productions = fields.Function(fields.One2Many('production', None,
        'Productions'), 'get_productions')

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls._error_messages.update({
                'missing_cost_plan': (
                    'The line "%(line)s" of sale "%(sale)s" doesn\'t have '
                    'Cost Plan, so it won\'t generate any production.'),
                })

    @classmethod
    def confirm(cls, sales):
        for sale in sales:
            for line in sale.lines:
                if (line.type == 'line' and line.product
                        and not getattr(line.product, 'purchasable', False)
                        and not line.cost_plan):
                    cls.raise_user_warning('missing_cost_plan%s' % sale.id,
                        'missing_cost_plan', {
                            'sale': sale.rec_name,
                            'line': line.rec_name,
                            })
        super(Sale, cls).confirm(sales)

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
                # TODO: move this code to sale line get_produtions() method
                production.cost_plan = line.cost_plan
                production.origin = str(line)
                production.reference = self.reference
                if (hasattr(production.product, 'quality_template') and
                        production.product.quality_template):
                    production.quality_template = (
                        production.product.quality_template)
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
            ('product', '=', Eval('product', 0)),
            ],
        states={
            'invisible': Eval('type') != 'line',
            },
        depends=['type', 'product'])
    productions = fields.One2Many('production', 'origin', 'Productions')

    @fields.depends('cost_plan', 'product')
    def on_change_product(self):
        CostPlan = Pool().get('product.cost.plan')
        plan = None
        if self.product:
            plans = CostPlan.search([('product', '=', self.product.id)],
                order=[('number', 'DESC')], limit=1)
            if plans:
                plan = plans[0]
                self.cost_plan = plan
        res = super(SaleLine, self).on_change_product()
        res['cost_plan'] = plan.id if plan else None
        return res

    def get_productions(self):
        if not self.cost_plan:
            return []
        if len(self.productions) > 0:
            return []
        # TODO: It will be better, to improve modularity, to call a sale.line
        # method
        return self.cost_plan.get_productions(self.sale.warehouse, self.unit,
            self.quantity)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['productions'] = None
        return super(SaleLine, cls).copy(lines, default=default)
