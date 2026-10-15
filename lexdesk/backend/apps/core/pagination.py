from rest_framework.pagination import PageNumberPagination


class Pagination(PageNumberPagination):
    """25 a page; apps may ask for up to 200 (a month's diary, a team list)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
