from os import path
from urllib.parse import urlunparse, urlparse 
from django.conf import settings
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from .pagination import Turnpage

class TurnpageModelMixin():
    '''为视图类`ViewSet`混入翻页功能
    '''
    def get_turnpage_respone(self, turnpage, request, view):
        if not turnpage.current:
            return Response({'detail': '没有数据了'}, status=status.HTTP_404_NOT_FOUND)

        uri = request.build_absolute_uri()
        original_uri_map = getattr(view, 'original_uri_map', None) or getattr(settings, 'ORIGINAL_URI_MAP', None)        
        urlparts = list(urlparse(uri))
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


        serializer_class = self.get_serializer_class()

        basepath = path.dirname(path.dirname(urlparts[2].rstrip('/')))
        nexturi = None
        if turnpage.next:
            urlparts[2] = '/'.join((basepath, turnpage.next.id, 'turnpage/'))
            nexturi = urlunparse(urlparts)

        prevuri = None
        if turnpage.previous:
            urlparts[2] = '/'.join((basepath, turnpage.previous.id, 'turnpage/'))
            prevuri = urlunparse(urlparts)

        serializer = serializer_class(turnpage.current)     
        return Response({
            'next': nexturi,
            'previous': prevuri,
            'data': serializer.data
        })
        

    @action(detail=True, methods=['get'])
    def next(self, request, pk=None):
        queryset = self.filter_queryset(self.get_queryset())
        turnpage = Turnpage(queryset, pk)
        serializer_class = self.get_serializer_class()
        if turnpage.next:
            serializer = serializer_class(turnpage.next)
            return Response(serializer.data)
        return Response({'detail': '没有数据了'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'])
    def previous(self, request, pk=None):
        queryset = self.filter_queryset(self.get_queryset())
        turnpage = Turnpage(queryset, pk)
        serializer_class = self.get_serializer_class()
        if turnpage.previous:
            serializer = serializer_class(turnpage.previous)
            return Response(serializer.data)
        return Response({'detail': '没有数据了'}, status=status.HTTP_404_NOT_FOUND) 

    @action(detail=True, methods=['get'])
    def turnpage(self, request, pk=None):
        queryset = self.filter_queryset(self.get_queryset())
        turnpage = Turnpage(queryset, pk)
        return self.get_turnpage_respone(turnpage, request, self)