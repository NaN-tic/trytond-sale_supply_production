# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from functools import wraps
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard
from trytond.i18n import gettext
from trytond.exceptions import UserError

def process_sale():
    def _process_sale(func):
        @wraps(func)
        def wrapper(cls, productions):
            pool = Pool()
            Sale = pool.get('sale.sale')
            SaleLine = Pool().get('sale.line')
            transaction = Transaction()
            context = transaction.context
            with transaction.set_context(_check_access=False):
                sales = list(set([p.origin.sale for p in productions
                            if p.origin and isinstance(p.origin, SaleLine)]))
            func(cls, productions)
            if sales:
                with transaction.set_context(
                        queue_batch=context.get('queue_batch', True)):
                    Sale.__queue__.process(sales)
        return wrapper
    return _process_sale


class Production(metaclass=PoolMeta):
    __name__ = 'production'

    @classmethod
    def _get_origin(cls):
        return super()._get_origin() | {'sale.line'}

    @classmethod
    @process_sale()
    def delete(cls, productions):
        super().delete(productions)


class ChangeQuantityStart(ModelView):
    'Change Production Quantity - Start'
    __name__ = 'production.change_quantity.start'

    production = fields.Many2One('production', 'Production', readonly=True)
    sale_line = fields.Many2One('sale.line', 'Sale Line', readonly=True)
    current_quantity = fields.Float('Current Quantity',
        digits='uom', readonly=True)
    new_quantity = fields.Float('New Quantity',
        digits='uom', required=True,
        domain=[
            ('new_quantity', '!=', Eval('current_quantity')),
            ('new_quantity', '>', 0),
            ],
        depends=['current_quantity'])
    uom = fields.Many2One('product.uom', 'Uom', readonly=True)


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
        sale_change_quantity.transition_modify()
        return 'end'
