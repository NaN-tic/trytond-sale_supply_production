from trytond.tests.tools import activate_modules
from trytond.modules.account_invoice.tests.tools import set_fiscalyear_invoice_sequences, create_payment_term
from trytond.modules.account.tests.tools import create_fiscalyear, create_chart, get_accounts
from trytond.modules.company.tests.tools import create_company, get_company
from proteus import Model, Wizard
from decimal import Decimal
import unittest
from trytond.tests.test_tryton import drop_db


class Test(unittest.TestCase):
    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        activate_modules(['sale_supply_production', 'sale_change_quantity'])

        # Create company::
        _ = create_company()
        company = get_company()

        # Create fiscal year::
        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')

        # Create chart of accounts::
        _ = create_chart(company)
        accounts = get_accounts(company)
        revenue = accounts['revenue']
        expense = accounts['expense']

        # Create parties::
        Party = Model.get('party.party')
        supplier = Party(name='Supplier')
        supplier.save()
        customer = Party(name='Customer')
        customer.save()

        # Create payment term::
        payment_term = create_payment_term()
        payment_term.save()

        # Configure production location::
        Location = Model.get('stock.location')
        warehouse, = Location.find([('code', '=', 'WH')])
        production_location, = Location.find([('code', '=', 'PROD')])
        warehouse.production_location = production_location
        warehouse.save()

        # Create account category::
        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name="Account Category")
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.save()

        # Create product::
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'product'
        template.default_uom = unit
        template.type = 'goods'
        template.producible = True
        template.supply_production_on_sale = True
        template.salable = True
        template.list_price = Decimal(30)
        template.account_category = account_category
        template.save()
        product, = template.products
        product.cost_price = Decimal(20)
        product.cost_price_method = 'fixed'
        product.save()

        # Create Components::
        meter, = ProductUom.find([('symbol', '=', 'm')])
        centimeter, = ProductUom.find([('symbol', '=', 'cm')])
        templateA = ProductTemplate()
        templateA.name = 'component A'
        templateA.default_uom = meter
        templateA.type = 'goods'
        templateA.list_price = Decimal(2)
        templateA.save()
        componentA, = templateA.products
        componentA.cost_price = Decimal(1)
        componentA.save()
        templateB = ProductTemplate()
        templateB.name = 'component B'
        templateB.default_uom = meter
        templateB.type = 'goods'
        templateB.list_price = Decimal(2)
        templateB.save()
        componentB, = templateB.products
        componentB.cost_price = Decimal(1)
        componentB.save()
        template1 = ProductTemplate()
        template1.name = 'component 1'
        template1.default_uom = unit
        template1.type = 'goods'
        template1.list_price = Decimal(5)
        template1.producible = True
        template1.save()
        component1, = template1.products
        component1.cost_price = Decimal(2)
        component1.save()
        template2 = ProductTemplate()
        template2.name = 'component 2'
        template2.default_uom = meter
        template2.type = 'goods'
        template2.list_price = Decimal(7)
        template2.cost_price = Decimal(5)
        template2.save()
        component2, = template2.products
        component2.cost_price = Decimal(5)
        component2.save()

        # Create Bill of Material::
        BOM = Model.get('production.bom')
        BOMInput = Model.get('production.bom.input')
        BOMOutput = Model.get('production.bom.output')
        component_bom = BOM(name='component1')
        input1 = BOMInput()
        component_bom.inputs.append(input1)
        input1.product = componentA
        input1.quantity = 1
        input2 = BOMInput()
        component_bom.inputs.append(input2)
        input2.product = componentB
        input2.quantity = 1
        output = BOMOutput()
        component_bom.outputs.append(output)
        output.product = component1
        output.quantity = 1
        component_bom.save()
        ProductBom = Model.get('product.product-production.bom')
        component1.boms.append(ProductBom(bom=component_bom))
        component1.save()
        bom = BOM(name='product')
        input1 = BOMInput()
        bom.inputs.append(input1)
        input1.product = component1
        input1.quantity = 5
        input2 = BOMInput()
        bom.inputs.append(input2)
        input2.product = component2
        input2.quantity = 150
        input2.unit = centimeter
        output = BOMOutput()
        bom.outputs.append(output)
        output.product = product
        output.quantity = 1
        bom.save()
        ProductBom = Model.get('product.product-production.bom')
        product.boms.append(ProductBom(bom=bom))
        product.save()

        # Sale product::
        Sale = Model.get('sale.sale')
        SaleLine = Model.get('sale.line')
        sale = Sale()
        sale.party = customer
        sale.payment_term = payment_term
        sale.invoice_method = 'order'
        sale_line = SaleLine()
        sale.lines.append(sale_line)
        sale_line.product = product
        sale_line.quantity = 2.0
        sale.click('quote')
        sale.click('confirm')
        self.assertEqual(sale.state, 'processing')
        sale_line, = sale.lines
        production, = sale.productions
        self.assertEqual(production.product, product)
        self.assertEqual(production.quantity, 2.0)
        self.assertEqual(len(production.inputs), 2)
        self.assertEqual(len(production.outputs), 1)

        # Increase quantity and check production is updated::
        change = Wizard('sale.change_line_quantity', [sale])
        change.form.line = sale_line
        change.form.new_quantity = 4.0
        change.execute('modify')
        sale.reload()
        sale_line, = sale.lines
        self.assertEqual(sale_line.confirmed_quantity, 2.0)
        self.assertEqual(sale_line.quantity, 4.0)
        production, = sale.productions
        self.assertEqual(production.quantity, 4.0)
