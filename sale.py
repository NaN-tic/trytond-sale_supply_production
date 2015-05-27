# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction
from .tools import prepare_vals

__all__ = ['Sale', 'SaleLine', 'ChangeLineQuantityStart', 'ChangeLineQuantity']
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


class ChangeLineQuantityStart:
    __name__ = 'sale.change_line_quantity.start'

    def on_change_with_minimal_quantity(self):
        pool = Pool()
        Uom = pool.get('product.uom')

        minimal_quantity = super(ChangeLineQuantityStart,
            self).on_change_with_minimal_quantity()

        produced_quantity = 0
        productions = self.line.productions if self.line else []
        for production in productions:
            if production.state in ('assigned', 'running', 'done', 'cancel'):
                produced_quantity += Uom.compute_qty(production.uom,
                    production.quantity, self.line.unit)

        return max(minimal_quantity, produced_quantity)


class ChangeLineQuantity:
    __name__ = 'sale.change_line_quantity'

    @classmethod
    def __setup__(cls):
        super(ChangeLineQuantity, cls).__setup__()
        cls._error_messages.update({
                'quantity_already_produced': 'Quantity already produced!',
                'no_updateable_productions': ('There is no updateable '
                    'production available!'),
                })

    def transition_modify(self):
        line = self.start.line
        if (line.quantity != self.start.new_quantity
                and line.sale.state == 'processing'):
            self.update_production()
        return super(ChangeLineQuantity, self).transition_modify()

    def update_production(self):
        pool = Pool()
        Production = pool.get('production')
        Uom = pool.get('product.uom')

        line = self.start.line
        quantity = self.start.new_quantity

        for production in line.productions:
            if production.state in ('assigned', 'running', 'done', 'cancel'):
                quantity -= Uom.compute_qty(production.uom,
                    production.quantity, self.start.line.unit)
        if quantity < 0:
            self.raise_user_error('quantity_already_produced')

        updateable_productions = self.get_updateable_productions()
        if quantity >= line.unit.rounding:
            production = updateable_productions.pop(0)
            self._change_production_quantity(
                production,
                Uom.compute_qty(line.unit, quantity, production.uom))
            production.save()
        if updateable_productions:
            Production.delete(updateable_productions)

    def _change_production_quantity(self, production, quantity):
        pool = Pool()
        Move = pool.get('stock.move')
        Operation = None
        try:
            Operation = pool.get('production.operation')
        except KeyError:
            pass

        production.quantity = quantity
        if getattr(production, 'route'):
            changes = production.update_operations()
            if changes and changes.get('operations'):
                if changes['operations'].get('remove'):
                    Operation.delete(
                        [Operation(o) for o in changes['operations']['remove']])
                production.operations = []
                for _, operation_vals in changes['operations']['add']:
                    operation_vals = prepare_vals(operation_vals)
                    production.operations.append(Operation(**operation_vals))
        if production.bom:
            production.inputs = []
            production.outputs = []
            changes = production.explode_bom()
            for _, input_vals in changes['inputs']['add']:
                production.inputs.append(Move(**input_vals))
            for _, output_vals in changes['outputs']['add']:
                production.outputs.append(Move(**output_vals))
        production.save()

    def get_updateable_productions(self):
        productions = sorted(
            [p for p in self.start.line.productions
                if p.state in ('draft', 'waiting')],
            key=self._production_key)
        if not productions:
            self.raise_user_error('no_updateable_productions')
        return productions

    def _production_key(self, production):
        return -production.quantity
