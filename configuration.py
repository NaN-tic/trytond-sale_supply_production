from trytond.model import fields, ModelSQL
from trytond.pool import PoolMeta
from trytond.modules.company.model import (
    CompanyMultiValueMixin, CompanyValueMixin)
from trytond.pyson import Eval


class Configuration(metaclass=PoolMeta):
    __name__ = 'sale.configuration'
    sale_supply_production_default = fields.Boolean(
        'Sale Line Supply Production',
        help='Default Supply Production value for Sale Lines')


class ConfigurationProductionWork(CompanyMultiValueMixin, metaclass=PoolMeta):
    __name__ = 'sale.configuration'

    default_work_center = fields.MultiValue(
        fields.Many2One('production.work.center', 'Default Work Center',
            domain=[
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ],
            help='Default Work Center for the Productions created from Sales'))


class ConfigurationDefaultWorkCenter(ModelSQL, CompanyValueMixin):
    "Default Work Center Configuration"
    __name__ = 'sale.configuration.default_work_center'

    default_work_center = fields.Many2One('production.work.center',
        'Default Work Center', domain=[
            ('company', 'in',
                [Eval('context', {}).get('company', -1), None]),
            ],
        help='Default Work Center for the Productions created from Sales')
