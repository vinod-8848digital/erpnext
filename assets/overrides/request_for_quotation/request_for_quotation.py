from erpnext.buying.doctype.request_for_quotation.request_for_quotation import RequestforQuotation
from assets.controllers.overrides.buying_controller import AssetsBuyingController


class AssetsRequestForQuotation(RequestforQuotation, AssetsBuyingController):
    pass
