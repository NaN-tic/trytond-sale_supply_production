# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard
from trytond.i18n import gettext
from trytond.exceptions import UserError

__all__ = ['Production', 'ChangeQuantityStart', 'ChangeQuantity']

class Production(metaclass=PoolMeta):
    __name__ = 'production'

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        origins = super(Production, cls)._get_origin()
        origins.append('sale.line')
        return origins


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
        'sale_supply_production.production_change_quantity_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Modify', 'modify', 'tryton-ok', default=True),
            ])
    modify = StateTransition()

    def default_start(self, fields):
        pool = Pool()
        Production = pool.get('production')
        SaleLine = Pool().get('sale.line')

        production = Production(Transaction().context['active_id'])
        if production.state not in ('draft', 'waiting'):
            raise UserError(gettext(
                'sale_supply_production.invalid_production_state',
                production=production.rec_name))
        if not isinstance(production.origin, SaleLine):
            raise UserError(gettext(
                'sale_supply_production._no_related_to_sale'))

        productions = Production.search(['origin','=', str(production.origin)])
        if len(productions) != 1:
            raise UserError(gettext(
                'sale_supply_production.production_with_same_origin',
                productions=",".join([x.rec_name for x in productions]),
                sale_line=production.origin.rec_name))

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
