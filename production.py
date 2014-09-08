#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Production', 'Plan', 'PlanBOM']
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
                #Create production for current product
                plan_bom = plan_boms[input_product.id]
                prod = plan_bom.get_production_data()
                prod['quantity'] = Input.compute_quantity(input_, factor)
                prod['uom'] = input_.uom
                res.append(prod)
                #Search for more chained productions
                res.extend(self._get_chained_productions(input_product,
                        plan_bom.bom, quantity, input_.uom))
        return res

    def get_production_data(self):
        return {'product': self.product, 'bom': self.bom}

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
        production.state = 'request'
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
                for index, operation_vals in changes['operations']['add']:
                    production.operations.append(Operation(**operation_vals))

        if 'bom' in values:
            production.bom = values['bom']
            production.inputs = []
            production.outputs = []
            changes = production.explode_bom()
            for index, input_vals in changes['inputs']['add']:
                production.inputs.append(Move(**input_vals))
            for index, output_vals in changes['outputs']['add']:
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
