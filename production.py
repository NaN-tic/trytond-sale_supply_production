# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard
from .tools import prepare_vals

__all__ = ['Production', 'Plan', 'PlanBOM',
    'ChangeQuantityStart', 'ChangeQuantity']
__metaclass__ = PoolMeta


class Production:
    __name__ = 'production'

    cost_plan = fields.Many2One('product.cost.plan', 'Cost Plan',
        states={
            'readonly': ~Eval('state').in_(['request', 'draft']),
            },
        depends=['state'])

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        origins = super(Production, cls)._get_origin()
        origins.append('sale.line')
        return origins


class Plan:
    __name__ = 'product.cost.plan'

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls._error_messages.update({
                'cannot_create_productions_missing_bom': ('No production can '
                    'be created because Product Cost Plan "%s" has no BOM '
                    'assigned.')
                })

    def get_productions(self, warehouse, unit, quantity):
        "Returns a list of productions to create for the cost plan"
        if not self.bom:
            self.raise_user_error('cannot_create_productions_missing_bom',
                self.rec_name)
        productions = []

        prod_data = self.get_elegible_productions(unit, quantity)
        # The first production in prod_data is the "main" production
        if hasattr(self, 'route'):
            prod_data[0]['route'] = self.route
        if hasattr(self, 'process'):
            prod_data[0]['process'] = self.process

        for data in prod_data:
            data['warehouse'] = warehouse
            productions.append(self._get_production(data))

        return productions

    def get_elegible_productions(self, unit, quantity):
        """
        Returns a list of dicts with the required data to create all the
        productions required for this plan
        """
        res = []

        prod = self.get_production_data()
        prod['uom'] = unit
        prod['quantity'] = quantity
        res.append(prod)

        res.extend(self._get_chained_productions(self.product, self.bom,
                quantity, unit))
        return res

    def _get_chained_productions(self, product, bom, quantity, unit):
        "Returns chained productions to produce product"
        pool = Pool()
        Input = pool.get('production.bom.input')
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
                prod = plan_bom.get_production_data()
                prod['quantity'] = Input.compute_quantity(input_, factor)
                prod['uom'] = input_.uom
                res.append(prod)
                # Search for more chained productions
                res.extend(self._get_chained_productions(input_product,
                        plan_bom.bom, quantity, input_.uom))
        return res

    def get_production_data(self):
        return {
            'product': self.product,
            'bom': self.bom,
            }

    def _get_production(self, values):
        "Returns the production values to create for the especified bom"
        pool = Pool()
        Company = pool.get('company.company')
        Move = pool.get('stock.move')
        Production = pool.get('production')
        Operation = None
        try:
            Operation = pool.get('production.operation')
        except KeyError:
            pass

        context = Transaction().context

        production = Production()
        production.company = Company(context.get('company'))
        production.state = 'draft'
        production.quantity = values['quantity']
        production.product = values['product']

        if 'uom' in values:
            production.uom = values['uom']
        else:
            production.uom = production.product.default.uom

        warehouse = values['warehouse']
        production.warehouse = warehouse
        production.location = warehouse.production_location

        if 'process' in values:
            production.process = values['process']

        if 'route' in values:
            production.route = values['route']
            if Operation:
                production.operations = []
                changes = production.update_operations()
                for _, operation_vals in changes['operations']['add']:
                    operation_vals = prepare_vals(operation_vals)
                    production.operations.append(Operation(**operation_vals))

        if 'bom' in values:
            production.bom = values['bom']
            production.inputs = []
            production.outputs = []
            changes = production.explode_bom()
            for _, input_vals in changes['inputs']['add']:
                production.inputs.append(Move(**input_vals))
            for _, output_vals in changes['outputs']['add']:
                production.outputs.append(Move(**output_vals))
        return production


class PlanBOM:
    __name__ = 'product.cost.plan.bom_line'

    def get_production_data(self):
        if not self.bom:
            return
        return {
            'product': self.product,
            'bom': self.bom,
            }


class ChangeQuantityStart(ModelView):
    'Change Production Quantity - Start'
    __name__ = 'production.change_quantity.start'

    production = fields.Many2One('production', 'Production', readonly=True)
    sale_line = fields.Many2One('sale.line', 'Sale Line', readonly=True)
    current_quantity = fields.Float('Current Quantity',
        digits=(16, Eval('unit_digits', 2)), readonly=True,
        depends=['unit_digits'])
    new_quantity = fields.Float('New Quantity',
        digits=(16, Eval('unit_digits', 2)), required=True,
        domain=[
            ('new_quantity', '!=', Eval('current_quantity')),
            ('new_quantity', '>', 0),
            ],
        depends=['unit_digits', 'current_quantity'])
    uom = fields.Many2One('product.uom', 'Uom', readonly=True)
    unit_digits = fields.Integer('Unit Digits', readonly=True)


class ChangeQuantity(Wizard):
    'Change Production Quantity'
    __name__ = 'production.change_quantity'

    start = StateView('production.change_quantity.start',
        'sale_cost_plan.production_change_quantity_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Modify', 'modify', 'tryton-ok', default=True),
            ])
    modify = StateTransition()

    @classmethod
    def __setup__(cls):
        super(ChangeQuantity, cls).__setup__()
        cls._error_messages.update({
                'invalid_production_state': (
                    'You cannot modify the quantity of Production "%s" '
                    'because it is not in state "Draft" or "Waiting".'),
                'production_no_related_to_sale': (
                    'The Production "%s" is not related to any sale.\n'
                    'In this case, you can\'t use this wizard but you can '
                    'modify the quantity directly in production\'s form.'),
                })

    def default_start(self, fields):
        pool = Pool()
        Production = pool.get('production')
        SaleLine = Pool().get('sale.line')

        production = Production(Transaction().context['active_id'])
        if production.state not in ('draft', 'waiting'):
            self.raise_user_error('invalid_production_state',
                production.rec_name)
        if not isinstance(production.origin, SaleLine):
            self.raise_user_error('production_no_related_to_sale')
        return {
            'production': production.id,
            'sale_line': production.origin.id,
            'current_quantity': production.quantity,
            'uom': production.uom.id,
            'unit_digits': production.uom.digits,
            }

    def transition_modify(self):
        pool = Pool()
        Uom = pool.get('product.uom')
        SaleChangeLineQuantity = pool.get('sale.change_line_quantity',
            type='wizard')

        sale_line = self.start.sale_line
        sale_line_new_quantity = (sale_line.quantity
            + Uom.compute_qty(
                self.start.uom,
                self.start.new_quantity - self.start.current_quantity,
                sale_line.unit))

        sale_change_quantity = SaleChangeLineQuantity(self._session_id)
        sale_change_quantity.start.sale = sale_line.sale
        sale_change_quantity.start.line = sale_line
        sale_change_quantity.start.current_quantity = sale_line.quantity
        sale_change_quantity.start.new_quantity = sale_line_new_quantity
        sale_change_quantity.start.unit = sale_line.unit
        sale_change_quantity.start.unit_digits = sale_line.unit.digits
        sale_change_quantity.transition_modify()
        return 'end'
