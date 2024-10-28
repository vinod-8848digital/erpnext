from erpnext.buying.doctype.supplier_quotation.supplier_quotation import SupplierQuotation
from assets.controllers.overrides.buying_controller import AssetsBuyingController


class AssetsSupplierQuotation(SupplierQuotation, AssetsBuyingController):
    pass
