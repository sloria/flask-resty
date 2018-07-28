import operator

from marshmallow import fields, Schema
import pytest

from flask_resty import (
    Api,
    Filtering,
    GenericModelView,
    PagePagination,
    RelayCursorPagination,
    Sorting,
)

# -----------------------------------------------------------------------------

try:
    from apispec import APISpec
    from flask_resty.spec import FlaskRestyPlugin, ModelViewDeclaration
except ImportError:
    pytestmark = pytest.mark.skip(reason="apispec support not installed")

# -----------------------------------------------------------------------------


@pytest.fixture
def schemas():
    class FooSchema(Schema):
        id = fields.Integer(as_string=True)
        name = fields.String(required=True)
        color = fields.String()

    return {
        'foo': FooSchema,
    }


@pytest.fixture
def views(schemas):
    class FooViewBase(GenericModelView):
        schema = schemas['foo']()

    class FooListView(FooViewBase):
        spec_declaration = ModelViewDeclaration(many=True)

        filtering = Filtering(
            color=operator.eq,
        )
        sorting = Sorting('name', 'color')
        pagination = PagePagination(2)

        def get(self):
            pass

        def post(self):
            """test the docstring"""
            pass

    class FooView(FooViewBase):
        def get(self, id):
            pass

        def put(self, id):
            pass

        def patch(self):
            pass

        def delete(self, id):
            pass

    class FooBazView(GenericModelView):
        spec_declaration = ModelViewDeclaration(tag=False)

        schema = schemas['foo']()

        def put(self, id):
            """baz a foo"""
            pass

    class BarView(GenericModelView):
        spec_declaration = ModelViewDeclaration(
            get={'200': {}},
            post={'204': {'description': 'request the creation of a new bar'}},
        )

        pagination = RelayCursorPagination(2)

        def get(self):
            pass

        def post(self):
            pass

        def put(self):
            """put a bar"""
            pass

    return {
        'foo_list': FooListView,
        'foo': FooView,
        'foo_baz': FooBazView,
        'bar': BarView,
    }


@pytest.fixture(autouse=True)
def routes(app, views):
    api = Api(app)
    api.add_resource('/foos', views['foo_list'], views['foo'])
    api.add_resource('/foos/<id>/baz', views['foo_baz'])
    api.add_resource('/bars', views['bar'])


@pytest.yield_fixture(autouse=True)
def ctx(app):
    with app.test_request_context():
        yield


@pytest.fixture
def spec(schemas, views):
    spec = APISpec(
        title='test api',
        version='0.1.0',
        plugins=(FlaskRestyPlugin(),),
    )

    spec.definition('Foo', schema=schemas['foo'])

    spec.add_path(view=views['foo_list'])
    spec.add_path(view=views['foo'])
    spec.add_path(view=views['foo_baz'])
    spec.add_path(view=views['bar'])

    return spec.to_dict()


# -----------------------------------------------------------------------------


def test_definition_autogeneration(views):
    spec = APISpec(
        title='test api',
        version='0.1.0',
        plugins=(FlaskRestyPlugin(),),
    )

    spec.add_path(view=views['foo_list'])

    assert 'FooSchema' in spec.to_dict()['definitions']


def test_tagging(views):
    spec = APISpec(
        title='test api',
        version='0.1.0',
        plugins=(FlaskRestyPlugin(),),
    )

    spec.add_path(view=views['foo_list'])

    assert 'FooSchema' in spec.to_dict()['paths']['/foos']['get']['tags']


def test_invalid_kwargs():
    with pytest.raises(TypeError) as excinfo:
        ModelViewDeclaration(putt=123)
    assert 'invalid keyword argument "putt"' == str(excinfo.value)


def test_schema_definitions(spec):
    assert spec['definitions']['Foo'] == {
        'type': 'object',
        'required': ['name'],
        'properties': {
            'id': {'type': 'integer', 'format': 'int32'},
            'name': {'type': 'string'},
            'color': {'type': 'string'},
        },
    }


def test_paths(spec):
    assert '/foos' in spec['paths']
    assert '/foos/{id}' in spec['paths']
    assert '/bars' in spec['paths']


def test_get_response(spec):
    foo_get = spec['paths']['/foos/{id}']['get']
    assert foo_get['responses'] == {
        '200': {
            'description': "",
            'schema': {
                'type': 'object',
                'properties': {
                    'data': {'$ref': '#/definitions/Foo'},
                },
            },
        },
    }


def test_get_list_response(spec):
    foos_get = spec['paths']['/foos']['get']
    assert foos_get['responses']['200']['schema']['properties']['data'] == {
        'type': 'array',
        'items': {'$ref': '#/definitions/Foo'},
    }


def test_get_pagination_meta(spec):
    foos_get = spec['paths']['/foos']['get']
    assert foos_get['responses']['200']['schema']['properties']['meta'] == {
        'type': 'object',
        'properties': {
            'has_next_page': {'type': 'boolean'},
        },
    }


def test_post_response(spec):
    foos_get = spec['paths']['/foos']['post']
    assert foos_get['responses'] == {
        '201': {'description': ''},
    }


def test_put_response(spec):
    foo_put = spec['paths']['/foos/{id}']['put']
    assert foo_put['responses'] == {
        '204': {'description': ''},
    }


def test_delete_response(spec):
    foo_delete = spec['paths']['/foos/{id}']['delete']
    assert foo_delete['responses'] == {
        '204': {'description': ""},
    }


def test_only_requested_methods(spec):
    assert set(spec['paths']['/foos'].keys()) == {'post', 'get'}
    assert set(spec['paths']['/foos/{id}'].keys()) == {
        'get',
        'put',
        'patch',
        'delete',
        'parameters',
    }
    assert set(spec['paths']['/bars'].keys()) == {'get', 'put', 'post'}


def test_path_params(spec):
    query_param = {
        'in': 'path',
        'required': True,
        'type': 'string',
        'name': 'id',
    }
    assert query_param in spec['paths']['/foos/{id}']['parameters']


def test_body_params(spec):
    foo_post = spec['paths']['/foos']['post']
    body = {
        'in': 'body',
        'name': 'FooPayload',
        'required': True,
        'schema': {
            'type': 'object',
            'required': ['data'],
            'properties': {
                'data': {'$ref': '#/definitions/Foo'},
            },
        },
    }
    assert body in foo_post['parameters']


def test_pagination(spec):
    foos_get = spec['paths']['/foos']['get']

    pars = (
        ('limit', "pagination limit"),
        ('offset', "pagination offset"),
        ('page', "page number"),
    )

    for parameter_name, description in pars:
        parameter = {
            'in': 'query',
            'name': parameter_name,
            'type': 'int',
            'description': description,
        }
        assert parameter in foos_get['parameters']


def test_sorting(spec):
    foos_get = spec['paths']['/foos']['get']

    parameter = {
        'in': 'query',
        'name': 'sort',
        'type': 'string',
        'description': "field to sort by",
    }
    assert parameter in foos_get['parameters']


def test_filters(spec):
    foos_get = spec['paths']['/foos']['get']

    parameter = {
        'in': 'query',
        'name': 'color',
        'type': 'string',
    }
    assert parameter in foos_get['parameters']


def test_docstring(spec):
    foos_post = spec['paths']['/foos']['post']
    assert foos_post['description'] == "test the docstring"


def test_schemaless(spec):
    bars_post = spec['paths']['/bars']['post']
    assert bars_post['responses'] == {
        '204': {
            'description': "request the creation of a new bar",
        },
    }

    bars_put = spec['paths']['/bars']['put']
    assert bars_put == {
        'responses': {},
        'parameters': [],
        'description': "put a bar",
    }


def test_relay_cursor_pagination(spec):
    bars_get = spec['paths']['/bars']['get']

    parameter = {
        'in': 'query',
        'name': 'cursor',
        'type': 'string',
        'description': "pagination cursor",
    }
    assert parameter in bars_get['parameters']
