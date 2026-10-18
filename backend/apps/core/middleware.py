from ipaddress import ip_address

from django.http.request import split_domain_port
from django.middleware.common import CommonMiddleware


class ProductionCommonMiddleware(CommonMiddleware):
    def process_request(self, request):
        if request.path_info == "/api/v1/health/" and request.method in {"GET", "HEAD"}:
            domain, _ = split_domain_port(request.META.get("HTTP_HOST", ""))
            try:
                address = ip_address(domain.strip("[]"))
            except ValueError:
                pass
            else:
                if address.is_private and not address.is_unspecified:
                    return None

        return super().process_request(request)
