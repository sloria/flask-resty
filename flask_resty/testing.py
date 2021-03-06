from collections import Mapping, Sequence
import json
import re

from flask.testing import FlaskClient

from .compat import basestring
from .utils import UNDEFINED

# -----------------------------------------------------------------------------


class ApiClient(FlaskClient):
    def open(self, path, *args, **kwargs):
        full_path = '{}{}'.format(
            self.application.extensions['resty'].api.prefix, path,
        )

        if 'data' in kwargs:
            kwargs.setdefault('content_type', 'application/json')
            if kwargs['content_type'] == 'application/json':
                kwargs['data'] = json.dumps({'data': kwargs['data']})

        return super(ApiClient, self).open(full_path, *args, **kwargs)


# -----------------------------------------------------------------------------


class Predicate(object):
    """A helper object to do predicate assertion"""

    def __init__(self, predicate):
        self.predicate = predicate

    def __eq__(self, other):
        return self.predicate(other)

    def __ne__(self, other):
        return not self.predicate(other)


def InstanceOf(type):
    return Predicate(lambda value: isinstance(value, type))


def Matching(expected_regex):
    return Predicate(re.compile(expected_regex).match)


def assert_shape(actual, expected):
    if isinstance(expected, Mapping):
        assert isinstance(actual, Mapping)
        # Unlike all the others, this checks that the actual items are a
        # superset of the expected items, rather than that they match.
        for key, value in expected.items():
            if value is not UNDEFINED:
                assert key in actual
                assert_shape(actual[key], value)
            else:
                assert key not in actual
    elif isinstance(expected, basestring):
        assert expected == actual
    elif isinstance(expected, Sequence):
        assert isinstance(actual, Sequence)
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected):
            assert_shape(actual_item, expected_item)
    elif isinstance(expected, float):
        assert abs(actual - expected) < 1e-6
    else:
        assert expected == actual


def Shape(expected):
    def predicate(actual):
        assert_shape(actual, expected)
        return True

    return Predicate(predicate)


# -----------------------------------------------------------------------------


def get_body(response):
    assert response.mimetype == 'application/json'
    return json.loads(response.get_data(as_text=True))


def get_data(response):
    return get_body(response)['data']


def get_errors(response):
    return get_body(response)['errors']


def get_meta(response):
    return get_body(response)['meta']


def assert_response(response, expected_status_code, expected_data=UNDEFINED):
    """Assert on the status and contents of a response.

    If specified, expected_data is checked against either the data or the
    errors in the response body, depending on the response status. This check
    ignores extra keys dictionaries in the response contents.
    """
    assert response.status_code == expected_status_code

    if expected_data is UNDEFINED:
        return

    if 200 <= response.status_code < 300:
        response_data = get_data(response)
    else:
        response_data = get_errors(response)

    if not isinstance(expected_data, Predicate):
        expected_data = Shape(expected_data)

    assert response_data == expected_data
