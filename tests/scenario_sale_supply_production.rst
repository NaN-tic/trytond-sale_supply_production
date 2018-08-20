=======================
Sale Cost Plan Scenario
=======================

=============
General Setup
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences, create_payment_term
    >>> from trytond.tests.tools import activate_modules
    >>> today = datetime.date.today()

Install product_cost_plan Module::

    >>> config = activate_modules(['sale_supply_production', 'sale_cost_plan'])

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Create sale user::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> purchase_user = User()
    >>> sale_user = User()
    >>> sale_user.name = 'Sale'
    >>> sale_user.login = 'sale'
    >>> sale_user.main_company = company
    >>> sale_group, = Group.find([('name', '=', 'Sales')])
    >>> sale_user.groups.append(sale_group)
    >>> sale_user.save()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> payable = accounts['payable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']
    >>> account_cash = accounts['cash']

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier')
    >>> supplier.save()
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Configuration production location::

    >>> Location = Model.get('stock.location')
    >>> warehouse, = Location.find([('code', '=', 'WH')])
    >>> production_location, = Location.find([('code', '=', 'PROD')])
    >>> warehouse.production_location = production_location
    >>> warehouse.save()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.producible = True
    >>> template.salable = True
    >>> template.list_price = Decimal(30)
    >>> template.cost_price_method = 'fixed'
    >>> template.account_category = account_category
    >>> template.save()
    >>> product, = template.products
    >>> product.cost_price = Decimal(20)
    >>> product.save()

    >>> template_s = ProductTemplate()
    >>> template_s.name = 'product'
    >>> template_s.default_uom = unit
    >>> template_s.type = 'goods'
    >>> template_s.producible = True
    >>> template_s.salable = True
    >>> template_s.list_price = Decimal(30)
    >>> template_s.cost_price_method = 'fixed'
    >>> template_s.account_category = account_category
    >>> template_s.save()
    >>> product_s, = template_s.products
    >>> product_s.cost_price = Decimal(20)
    >>> product_s.save()

Create Components::

    >>> meter, = ProductUom.find([('name', '=', 'Meter')])
    >>> centimeter, = ProductUom.find([('name', '=', 'centimeter')])
    >>> templateA = ProductTemplate()
    >>> templateA.name = 'component A'
    >>> templateA.producible = True
    >>> templateA.default_uom = meter
    >>> templateA.type = 'goods'
    >>> templateA.list_price = Decimal(2)
    >>> templateA.save()
    >>> componentA, = templateA.products
    >>> componentA.cost_price = Decimal(1)
    >>> componentA.save()

    >>> templateB = ProductTemplate()
    >>> templateB.name = 'component B'
    >>> templateB.producible = True
    >>> templateB.default_uom = meter
    >>> templateB.type = 'goods'
    >>> templateB.list_price = Decimal(2)
    >>> templateB.save()
    >>> componentB, = templateB.products
    >>> componentB.cost_price = Decimal(1)
    >>> componentB.save()

    >>> template1 = ProductTemplate()
    >>> template1.name = 'component 1'
    >>> template1.producible = True
    >>> template1.default_uom = unit
    >>> template1.type = 'goods'
    >>> template1.list_price = Decimal(5)
    >>> template1.save()
    >>> component1, = template1.products
    >>> component1.cost_price = Decimal(2)
    >>> component1.save()

    >>> template2 = ProductTemplate()
    >>> template2.name = 'component 2'
    >>> template2.producible = True
    >>> template2.default_uom = meter
    >>> template2.type = 'goods'
    >>> template2.list_price = Decimal(7)
    >>> template2.save()
    >>> component2, = template2.products
    >>> component2.cost_price = Decimal(5)
    >>> component2.save()

Create Bill of Material::

    >>> BOM = Model.get('production.bom')
    >>> BOMInput = Model.get('production.bom.input')
    >>> BOMOutput = Model.get('production.bom.output')
    >>> component_bom = BOM(name='component1')
    >>> input1 = BOMInput()
    >>> component_bom.inputs.append(input1)
    >>> input1.product = componentA
    >>> input1.quantity = 1
    >>> input2 = BOMInput()
    >>> component_bom.inputs.append(input2)
    >>> input2.product = componentB
    >>> input2.quantity = 1
    >>> output = BOMOutput()
    >>> component_bom.outputs.append(output)
    >>> output.product = component1
    >>> output.quantity = 1
    >>> component_bom.save()

    >>> ProductBom = Model.get('product.product-production.bom')
    >>> component1.boms.append(ProductBom(bom=component_bom))
    >>> component1.save()

    >>> bom = BOM(name='product')
    >>> input1 = BOMInput()
    >>> bom.inputs.append(input1)
    >>> input1.product = component1
    >>> input1.quantity = 5
    >>> input2 = BOMInput()
    >>> bom.inputs.append(input2)
    >>> input2.product = component2
    >>> input2.quantity = 150
    >>> input2.uom = centimeter
    >>> output = BOMOutput()
    >>> bom.outputs.append(output)
    >>> output.product = product
    >>> output.quantity = 1
    >>> bom.save()

    >>> ProductBom = Model.get('product.product-production.bom')
    >>> product.boms.append(ProductBom(bom=bom))
    >>> product.save()

Create a cost plan for product (without child boms)::

    >>> CostPlan = Model.get('product.cost.plan')
    >>> plan = CostPlan()
    >>> plan.product = product
    >>> plan.quantity = 1
    >>> plan.save()
    >>> CostPlan.compute([plan.id], config.context)
    >>> plan.reload()

Sale product with first plan::

    >>> config.user = sale_user.id
    >>> Sale = Model.get('sale.sale')
    >>> SaleLine = Model.get('sale.line')
    >>> sale = Sale()
    >>> sale.party = customer
    >>> sale.payment_term = payment_term
    >>> sale.invoice_method = 'order'
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.cost_plan = plan
    >>> sale_line.quantity = 2.0
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product
    >>> sale_line.quantity = 1.0
    >>> sale_line.supply_production = False
    >>> sale_line = SaleLine()
    >>> sale.lines.append(sale_line)
    >>> sale_line.product = product_s
    >>> sale_line.quantity = 1.0
    >>> sale_line.supply_production = False
    >>> sale.save()
    >>> Sale.quote([sale.id], config.context)
    >>> Sale.confirm([sale.id], config.context)
    >>> Sale.process([sale.id], config.context)
    >>> sale.state
    u'processing'
    >>> sale.reload()
    >>> len(sale.productions) == 1
    True
    >>> production, = sale.productions
    >>> production.product == product
    True
    >>> production.quantity == 2.0
    True

