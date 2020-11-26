import json
import base64
from urllib.parse import quote_from_bytes, unquote, urlunparse, urlparse, urlencode, parse_qs 
from django.conf import settings
from django.core.paginator import InvalidPage
from rest_framework import pagination, serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from django.core.paginator import Paginator

def get_queryset_ordering(queryset):
    '''返回QuerySet对象的排序方式
    '''
    if queryset.ordered:
        orderings = queryset.query.extra_order_by or queryset.query.order_by or queryset.query.get_meta().ordering
        ordering = orderings[0]
        if ordering[0] == '-':
            return (False, ordering[1:], ordering)
        elif ordering[0] == '+':
            return (True, ordering[1:], ordering)
        return (True, ordering, ordering)
    return None

def reverse_ordering(ordering):
    '''翻转排序字符串
    '''
    if ordering is None:
        return None
    if ordering[0] == '-':
        return ordering[1:]
    if ordering[0] == '+':
        return '-' + ordering[1:]
    return '-' + ordering

def get_next_record(queryset, current, prev=False):
    '''从记录集中返回指定记录的后一条记录
    '''
    ordering = get_queryset_ordering(queryset)
    new_ordering = []
    new_ordering.append(ordering[2])
    if ordering is None:
        ordering = (True, 'pk', 'pk')
        new_ordering = ['pk',]

    if not ordering[1] in ('pk', 'id'):
        if ordering[0]:
            new_ordering.append('pk')
        else:
            new_ordering.append('-pk')

    if prev:
        new_ordering[0] = reverse_ordering(new_ordering[0])
        if len(new_ordering) > 1:
             new_ordering[1] = reverse_ordering(new_ordering[1])
    
    queryset = queryset.order_by(*new_ordering)

    refer_id = current.pk
    refer_field = ordering[1]

    refer_val = getattr(current, refer_field, None)
    next = None
    if len(new_ordering) > 1:
        if refer_val is None:
            cond = {refer_field + '__isnull': True}
        else:
            cond = {refer_field: refer_val}

        if (ordering[0] and not prev) or (not ordering[0] and prev):
            cond['pk__gt'] = refer_id
        else:
            cond['pk__lt'] = refer_id 
        next = queryset.filter(**cond).first()
    
    if next:
        return next

    if refer_val is None:
        cond = cond = {refer_field + '__isnull': False}
        next = queryset.filter(**cond).first()

    if next:
        return next

    asc = not ordering[0] if prev else ordering[0]
    if asc:
        cond = {refer_field + '__gt': refer_val}
    else:
        cond = {refer_field + '__lt': refer_val}

    next = queryset.filter(**cond).first()
    return next

class HugePaginator(Paginator):
    '''超大数据表分页类
    适用于mysql数据库, 数据表应当有主键, 排序字段必须建立索引
    @object_list  QuerySet实例
    @per_page  每页最大记录数
    @orphans  孤儿记录数
    @allow_empty_first_page 是否允许首页空
    @query_id 查询ID
    '''
    def __init__(
        self, 
        object_list, 
        per_page, 
        orphans=0, 
        allow_empty_first_page=True, 
        query_id=None,
        serializer_class=None
        ):
        super().__init__(object_list, per_page, orphans, allow_empty_first_page)
        self.serializer_class = serializer_class
        self._count = None
        self._ordering_field = None
        self._ordering_asc = True
        self._middle_value = None
        self._middle_offset = None
        if query_id:
            qc = None
            try:
                qc = self._decode_query_id(query_id)
            except:
                pass
            if qc:
                self._count = qc[0]
                self._ordering_field = qc[1]
                self._ordering_asc = qc[2]
                self._middle_value = qc[3]
                self._middle_offset = qc[4]

    def _encode_query_id(
        self, 
        count, 
        ordering_field=None, 
        ordering_asc=None, 
        middle_value=None,
        middle_offset=None
        ):
        '''编码查询ID
        '''
        mval = middle_value
        
        if self.serializer_class and mval:  
            serializer = self.serializer_class() 
            fields = serializer.get_fields()
            serial_field = fields.get(ordering_field, None)
            if isinstance(serial_field, serializers.DateTimeField):
                serial_field = serializers.DateTimeField(format='iso-8601')
            if ordering_field: 
                mval = serial_field.to_representation(mval)

        jsonstr = json.dumps([
            count,
            ordering_field, 
            ordering_asc, 
            mval,
            middle_offset
            ])
        query_id = quote_from_bytes(base64.encodebytes(jsonstr.encode()))
        return query_id

    def _decode_query_id(self, query_id):
        '''解码查询ID
        '''
        qstr = unquote(query_id)
        jsonstr = base64.decodebytes(qstr.encode()).decode()
        qid = json.loads(jsonstr)
        if self.serializer_class:  
            serializer = self.serializer_class() 
            fields = serializer.get_fields()
            serial_field = fields.get(self._ordering_field, None)
            if isinstance(serial_field, serializers.DateTimeField):
                serial_field = serializers.DateTimeField(format='iso-8601')            
            if serial_field: 
                qid[3] = serial_field.to_representation(qid[3])
        return qid

    @property
    def count(self):
        if self._count is None:
            self._count = self.object_list.order_by().count()
    
        return self._count

    @property
    def query_id(self):
        return self._encode_query_id(
            self._count,
            self._ordering_field,
            self._ordering_asc,
            self._middle_value,
            self._middle_offset
        )

    def page(self, number):
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        ordering = get_queryset_ordering(self.object_list)
        new_ordering = []
        if ordering is None:
            # 如果没有排序，默认以主键排序
            ordering = (True, 'pk')
            new_ordering = ['pk']
        else:
            new_ordering.append(ordering[2])

        if not ordering[1] in ('pk', 'id'):
            if ordering[0]:
                new_ordering.append('pk')
            else:
                new_ordering.append('-pk')

        if self._ordering_asc != ordering[0] or self._ordering_field != ordering[1]:
            # 排序条件改变，中间参考记录失效
            self._middle_offset = None
            self._middle_value = None

        self._ordering_asc = ordering[0]
        self._ordering_field = ordering[1]

        a_order = [*new_ordering]
        b_order = []
        b_order.append(reverse_ordering(a_order[0]))
        if len(a_order)>1:
            b_order.append(reverse_ordering(a_order[1]))

        qset = self.object_list.order_by(*a_order)
        ids = []
        if self._middle_offset is None:
            # 没有中间参考记录，以记录集首尾为参考点
            mbottom = bottom
            mtop = top
            to_start = bottom 
            to_end = self.count - top
            if to_start > to_end:
                # 距离结束位置近，以结束位置为参考
                count = top - bottom
                mbottom = to_end
                mtop = mbottom + count
                qset = self.object_list.order_by(*b_order)
            qset = qset.only('pk').all()[mbottom:mtop]
            ids = list(qset.values_list('pk', flat=True))
        elif bottom <= self._middle_offset and top >= self._middle_offset:
            # 需要查询的页跨越中间参考记录
            hcount = top - self._middle_offset
            lcount = self._middle_offset - bottom  
            hcond = {}
            lcond = {}          
            if self._ordering_asc:
                hcond = {
                    self._ordering_field + '__gte': self._middle_value
                }
                lcond = {
                    self._ordering_field + '__lt': self._middle_value
                }          
            else:
                hcond = {
                    self._ordering_field + '__lte': self._middle_value
                }
                lcond = {
                    self._ordering_field + '__gt': self._middle_value
                }  

            hqset = qset.only('pk').filter(**hcond).all()[:hcount]
            ids.extend(list(hqset.values_list('pk', flat=True))) 
            lqset = qset.only('pk').filter(**lcond).order_by(*b_order).all()[:lcount]
            ids.extend(list(lqset.values_list('pk', flat=True).all()))                   

        elif bottom < self._middle_offset and (self._middle_offset - top) < bottom:
            # 需要查询的页在开始位置到中间参考记录之间，并且距离中间参考记录较近
            mbottom = self._middle_offset - top 
            mtop = self._middle_offset - bottom
            cond = {}
            if self._ordering_asc:
                cond = {
                    self._ordering_field + '__lt': self._middle_value
                }
            else:
                cond = {
                    self._ordering_field + '__gt': self._middle_value
                }                
            mqset = qset.only('pk').filter(**cond).order_by(*b_order)[mbottom:mtop]
            ids.extend(list(mqset.values_list('pk', flat=True)))

        elif bottom < self._middle_offset:
            # 需要查询的页在开始位置到中间参考记录之间，并且距离开始位置较近
            mqset = qset.only('pk').all()[bottom:top]
            ids.extend(list(mqset.values_list('pk', flat=True))) 

        elif (bottom - self._middle_offset) <= (self.count - top):
            # 需要查询的页在中间参考记录到结束位置之间，并且距离中间参考记录较近
            mbottom = bottom - self._middle_offset
            mtop = top - self._middle_offset
            cond = {}
            if self._ordering_asc:
                cond = {
                    self._ordering_field + '__gte': self._middle_value
                }
            else:
                cond = {
                    self._ordering_field + '__lte': self._middle_value
                }

            mqset = qset.only('pk').filter(**cond).all()[mbottom:mtop]
            ids.extend(list(mqset.values_list('pk', flat=True))) 

        else:
            # 需要查询的页在中间参考记录到结束位置之间，并且距离结束位置较近
            mbottom = self.count - top
            mtop = self.count - bottom   
            mqset = qset.only('pk').order_by(*b_order)[mbottom:mtop]          
            ids.extend(list(mqset.values_list('pk', flat=True))) 

        rset = self.object_list.model.objects.filter(pk__in=ids).order_by(*a_order)

        # 寻找新的中间记录
        aval = None
        bval = None
        mcount = 0 
        moffset = None
        mval = None
        for item in list(rset):
            xval = getattr(item, self._ordering_field, None)
            aval = bval
            bval = xval
            if aval is not None and bval is not None and  aval != bval:
                moffset = mcount
                mval = xval
            mcount += 1

        if mval is not None:
            self._middle_value = mval
            self._middle_offset = bottom + moffset
        elif (mcount == 1 and bval is not None) and ((bottom == 0 and self._middle_value is None) 
             or (self._middle_value != bval and (bottom - 1) == self._middle_offset)):
            self._middle_offset = bottom 
            self._middle_value = bval

        this_page = self._get_page(rset, number, self)
        this_page.query_id = self.query_id
        return this_page


class HugePagination(pagination.PageNumberPagination):
    """超大数据表分页类    
    """ 
    django_paginator_class = HugePaginator
    # 携带查询缓存ID的参数名
    query_id_param = 'query_id'  
    # 携带分页尺寸的参数名
    page_size_query_param = 'page_size'
    # 允许的最大分页尺寸
    max_page_size = 500
    # 默认分页尺寸
    page_size = 30

    def renew_url(self, urlparts, request, view):
        original_uri_map = getattr(view, 'original_uri_map', None) or getattr(settings, 'ORIGINAL_URI_MAP', None)
        if original_uri_map:
            maps = len(original_uri_map)
            if maps>=1:
                scheme = request.headers.get(original_uri_map[0], None)
                if scheme:
                    urlparts[0] = scheme
            if maps>=2:
                loc = request.headers.get(original_uri_map[1], None)
                if loc:
                    urlparts[1] = loc            
            if maps>=3:
                uripath = request.headers.get(original_uri_map[2], None)
                if uripath:
                    pp = list(urlparse(uripath))
                    urlparts[2] = pp[2]             
        return urlparts

    def _perfect_url(self, url):
        urlparts = list(urlparse(url))
        params = parse_qs(urlparts[4])
        qid = self.page.query_id
        if qid:
            params[self.query_id_param] = [qid,]
        urlparts[4] = urlencode(params, doseq=True)
        urlparts = self.renew_url(urlparts, self.request, self.view)
        return urlunparse(urlparts)

    def get_next_link(self):
        url = super().get_next_link()
        if url:
            return self._perfect_url(url)
        return url

    def get_previous_link(self):
        url = super().get_previous_link()
        if url:
            return self._perfect_url(url)
        return url

    def paginate_queryset(self, queryset, request, view=None):
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        query_id = request.query_params.get(self.query_id_param, None)

        paginator = self.django_paginator_class(
            queryset, 
            page_size, query_id=query_id, 
            serializer_class=view.get_serializer_class() if view else None
            )
        page_number = request.query_params.get(self.page_query_param, 1)
        if page_number in self.last_page_strings:
            page_number = paginator.num_pages

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(
                page_number=page_number, message=str(exc)
            )
            raise NotFound(msg)

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.view = view
        self.request = request
        return list(self.page)

    def get_paginated_response(self, data):
        return Response({
            'query_id': self.page.query_id,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'count': self.page.paginator.count,
            'page_count': self.page.paginator.num_pages,
            'page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'results': data
        })


class Turnpage():
    '''记录翻页控制
    '''
    def __init__(self, queryset, current=None):
        self.queryset = queryset
        self._next = None
        self._previous = None
        self._current = None
        if current:
            try:
                self._current = queryset.get(pk=current)
            except:
                pass

    @property
    def next(self):        
        if self._next:
            return self._next

        if self.current is None:
            self._next = None
            return self._next

        self._next = get_next_record(self.queryset, self.current)

        return self._next

    @property
    def previous(self):
        if self._previous:
            return self._previous

        if self.current is None:
            self._previous = None
            return self._previous

        self._previous = get_next_record(self.queryset, self.current, True)

        return self._previous

    @property
    def current(self):
        return self._current