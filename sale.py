# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction

from .tools import prepare_vals

__all__ = ['Sale', 'SaleLine', 'ChangeLineQuantityStart', 'ChangeLineQuantity']


class Sale:
    __name__ = 'sale.sale'
    __metaclass__ = PoolMeta
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
                        and hasattr(line, 'cost_plan') and not line.cost_plan):
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
        productions = []
        for line in self.lines:
            if line.supply_production:
                new_productions = line.create_productions()
                if new_productions:
                    productions += new_productions
        return productions

    def get_productions(self, name):
        productions = []
        for line in self.lines:
            productions.extend([p.id for p in line.productions])
        return productions


class SaleLine:
    __name__ = 'sale.line'
    __metaclass__ = PoolMeta
    supply_production = fields.Boolean('Supply Production')
    productions = fields.One2Many('production', 'origin', 'Productions')

    @staticmethod
    def default_supply_production():
        SaleConfiguration = Pool().get('sale.configuration')
        return SaleConfiguration(1).sale_supply_production_default

    @fields.depends('product')
    def on_change_product(self):
        super(SaleLine, self).on_change_product()

        if self.product:
            self.supply_production = self.product.producible


    def create_productions(self):
        pool = Pool()

        if (self.type != 'line'
                or not self.product
                or not self.product.template.producible
                or self.quantity <= 0
                or hasattr(self, 'cost_plan') and not self.cost_plan
                or len(self.productions) > 0):
            return

        if hasattr(self, 'cost_plan') and self.cost_plan:
            productions_values = self.cost_plan.get_elegible_productions(
                self.unit, self.quantity)
        else:
            production_values = {
                'product': self.product,
                'uom': self.unit,
                'quantity': self.quantity,
                }
            if hasattr(self.product, 'bom') and self.product.bom:
                production_values.update({'bom': self.product.bom})
            productions_values = [production_values]

        productions = []
        for production_values in productions_values:
            production = self.get_production(production_values)

            if production:
                if hasattr(production, 'bom') and production.bom:
                    production.inputs = []
                    production.outputs = []
                    production.explode_bom()

                if getattr(production, 'route', None):
                    Operation = pool.get('production.operation')
                    production.operations = []
                    changes = production.update_operations()
                    for _, operation_vals in changes['operations']['add']:
                        operation_vals = prepare_vals(operation_vals)
                        production.operations.append(
                            Operation(**operation_vals))

                production.save()
                productions.append(production)
        return productions

    def get_production(self, values):
        pool = Pool()
        Production = pool.get('production')

        production = Production()
        production.company = self.sale.company
        production.warehouse = self.warehouse
        production.location = self.warehouse.production_location
        if hasattr(self, 'cost_plan'):
            production.cost_plan = self.cost_plan
        production.origin = str(self)
        production.reference = self.sale.reference
        production.state = 'draft'
        production.product = values['product']
        production.quantity = values['quantity']
        production.uom = values.get('uom', production.product.default_uom)
        if hasattr(Production, 'stock_owner'):
            production.stock_owner = self.sale.party
        if (hasattr(Production, 'quality_template') and
                production.product.quality_template):
            production.quality_template = production.product.quality_template

        if 'process' in values:
            production.process = values['process']

        if 'route' in values:
            production.route = values['route']

        if 'bom' in values:
            production.bom = values['bom']
        return production

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['productions'] = None
        return super(SaleLine, cls).copy(lines, default=default)


class ChangeLineQuantityStart:
    __name__ = 'sale.change_line_quantity.start'
    __metaclass__ = PoolMeta

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
    __metaclass__ = PoolMeta

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
        Operation = None
        try:
            Operation = pool.get('production.operation')
        except KeyError:
            pass

        production.quantity = quantity
        if getattr(production, 'route', None):
            changes = production.update_operations()
            if changes and changes.get('operations'):
                if changes['operations'].get('remove'):
                    Operation.delete([
                            Operation(o)
                            for o in changes['operations']['remove']])
                production.operations = []
                for _, operation_vals in changes['operations']['add']:
                    operation_vals = prepare_vals(operation_vals)
                    production.operations.append(Operation(**operation_vals))
        if production.bom:
            production.inputs = []
            production.outputs = []
            production.explode_bom()
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
