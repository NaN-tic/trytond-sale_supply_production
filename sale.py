# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError, UserWarning

__all__ = ['Sale', 'SaleLine', 'ChangeLineQuantityStart', 'ChangeLineQuantity']


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'
    productions = fields.Function(fields.Many2Many('production', None, None,
        'Productions'), 'get_productions')

    @classmethod
    def confirm(cls, sales):
        Warning = Pool().get('res.user.warning')

        for sale in sales:
            warning_lines = False
            for line in sale.lines:
                if (line.type == 'line' and line.product
                        and not getattr(line.product, 'purchasable', False)
                        and hasattr(line, 'cost_plan') and not line.cost_plan):
                    warning_lines = True
                    break
            key = 'missing_cost_plan_%s' % sale.id
            if warning_lines and Warning.check(key):
                raise UserWarning(key,
                    gettext('sale_supply_production.missing_cost_plan',
                        sale=sale.rec_name))
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


class SaleLine(metaclass=PoolMeta):
    __name__ = 'sale.line'
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
        if (self.type != 'line'
                or not self.product
                or not self.product.template.producible
                or self.quantity <= 0
                or hasattr(self, 'cost_plan') and not self.cost_plan
                or len(self.productions) > 0):
            return []

        if hasattr(self, 'cost_plan') and self.cost_plan:
            productions_values = self.cost_plan.get_elegible_productions(
                self.unit, self.quantity)
        else:
            production_values = {
                'product': self.product,
                'uom': self.unit,
                'quantity': self.quantity,
                }
            if self.product.boms:
                product_bom = self.product.boms[0]
                production_values.update({'bom': product_bom.bom})
                if getattr(product_bom, 'route', None):
                    production_values.update({'route': product_bom.route})
                if getattr(product_bom, 'process', None):
                    production_values.update({'process': product_bom.process})
            productions_values = [production_values]

        productions = []
        for production_values in productions_values:
            production = self.get_production(production_values)

            if production:
                if getattr(production, 'bom', None):
                    production.inputs = []
                    production.outputs = []
                    production.explode_bom()

                if getattr(production, 'route', None):
                    production.operations = []
                    production.on_change_route()

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


class Plan:
    __name__ = 'product.cost.plan'

    def get_elegible_productions(self, unit, quantity):
        """
        Returns a list of dicts with the required data to create all the
        productions required for this plan
        """
        if not self.bom:
            raise UserError(gettext(
                'sale_supply_production.cannot_create_productions_missing_bom',
                cost_plan=self.rec_name))

        prod = {
            'product': self.product,
            'bom': self.bom,
            'uom': unit,
            'quantity': quantity,
            }
        if hasattr(self, 'route'):
            prod['route'] = self.route
        if hasattr(self, 'process'):
            prod['process'] = self.process

        res = [
            prod
            ]
        res.extend(self._get_chained_productions(self.product, self.bom,
                quantity, unit))
        return res

    def _get_chained_productions(self, product, bom, quantity, unit,
            plan_boms=None):
        "Returns base values for chained productions"
        pool = Pool()
        Input = pool.get('production.bom.input')

        if plan_boms is None:
            plan_boms = {}
            for plan_bom in self.boms:
                if plan_bom.bom:
                    plan_boms[plan_bom.product.id] = plan_bom

        factor = bom.compute_factor(product, quantity, unit)
        res = []
        for input_ in bom.inputs:
            input_product = input_.product
            if input_product.id in plan_boms:
                # Create production for current product
                plan_bom = plan_boms[input_product.id]
                prod = {
                    'product': plan_bom.product,
                    'bom': plan_bom.bom,
                    'uom': input_.uom,
                    'quantity': Input.compute_quantity(input_, factor),
                    }
                res.append(prod)
                # Search for more chained productions
                res.extend(self._get_chained_productions(input_product,
                        plan_bom.bom, quantity, input_.uom, plan_boms))
        return res


class ChangeLineQuantityStart(metaclass=PoolMeta):
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


class ChangeLineQuantity(metaclass=PoolMeta):
    __name__ = 'sale.change_line_quantity'

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
            raise UserError(gettext(
                'sale_supply_production.quantity_already_produced'))
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
        production.quantity = quantity
        if getattr(production, 'route', None):
            production.on_change_route()

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
            raise UserError(gettext(
                'sale_supply_production.no_updateable_productions'))
        return productions

    def _production_key(self, production):
        return -production.quantity
