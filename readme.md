# Hugepagination

Hugepagination提供了在Django REST framework框架下使用的分页类和模型视图单条记录翻页功能，主要针对mysql数据库百万级+数据表进行了优化。
+ HugePagination，大数据表分页类
+ TurnpageModelMixin，为视图类`ViewSet`混入单条记录翻页功能

### 依赖
+ django >= 2.2.0
+ djangorestframework >= 3.10.0
+ django-filter >= 2.2.0
### 打包发布
```shell
# 打包
python setup.py sdist bdist_wheel
# 上传
twine upload dist/*
```
### 安装
+ pip安装
```shell
pip install django-hugepagination
```
+ 源码安装
```shell
python setup.py install
```

### 分页类使用
分页类`HugePagination`必须与视图类`ModelViewSet`配合使用，后端数据库应当使用MySql数据库，可排序字段和查询条件字段应当建立索引。
```python
from hugepagination.pagination import HugePagination

class MyViewSet(viewsets.ModelViewSet):
    queryset = MyModel.objects.all()
    serializer_class = MyModelSerializer
    pagination_class = HugePagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ['name','create_time']
    filterset_fields = ['name','create_time']
```
### 单条翻页功能（上一条，下一条）
`TurnpageModelMixin`为视图类`ModelViewSet`混入单条翻页功能，这个功能是列表视图的扩展，视图类增加如下方法：
#### next
查询指定记录的下一条记录，URL格式如下：
```
http://127.0.0.1/resources/1/next/ordering=create_time&name=taobao
```
返回数据格式:
```json
{
    "name": "taobao",
    ...
    "create_time": "2020-10-10 12:12:01"
}
```
#### previous
查询指定记录的下一条记录，URL格式如下：
```
http://127.0.0.1/resources/1/previous/ordering=create_time&name=taobao
```
返回数据格式同上
#### turnpage
查询指定ID的记录数据，同时返回该记录的上一条和下一条查询URL，URL格式如下：
```
http://127.0.0.1/resources/5/turnpage/ordering=create_time&name=taobao
```
返回数据格式如下：
```json
{
    "next": "http://127.0.0.1/resources/4/turnpage/ordering=create_time&name=taobao",
    "previous": "http://127.0.0.1/resources/6/turnpage/ordering=create_time&name=taobao",
    "data": {
        "name": "taobao",
        ...
        "create_time": "2020-10-10 12:12:01"        
    }
}
```
#### 代码示例
```python
from hugepagination.pagination import HugePagination, TurnpageModelMixin

class MyViewSet(viewsets.ModelViewSet, TurnpageModelMixin):
    queryset = MyModel.objects.all()
    serializer_class = MyModelSerializer
    pagination_class = HugePagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ['name','create_time']
    filterset_fields = ['name','create_time']
```
#### WEB服务器存在URL重写或者反向代理，返回URL与实际访问URL不一致，处理方法
在django配置文件中增加配置项`ORIGINAL_URI_MAP`，该配置是`list`，包含三个元素，依次指定包含源请求URL的`scheme`，`host`，`path`三个部分的http header。响应结果将根据http header修改。
```python
ORIGINAL_URI_MAP = ['X-Scheme','X-Forwarded-Host','X-Original-Uri']
```
也可以在视图中配置属性`original_uri_map`，格式通上。
视图中属性优先于配置文件。
### 注意事项
+ 如果要保持列表显示记录的顺序和翻页显示记录的顺序一致，那么排序条件和筛选条件应当与列表查询保持一致。
+ 翻页查询使用`next`和`previous`方法，应当避免在获取上一条和下一条前修改当前记录的排序字段值；这种情况建议用`turnpage`方法。
