from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Thread

from xboto.client import ssm
from xboto.dependencies import BotoClients

DEFAULT_ENDPOINT = 'https://ssm.us-east-1.amazonaws.com'


def _in_new_thread(func):
    """ xinject keeps what's injected in a `ContextVar`, so the thread starts with a copy of this one's. """
    result = {}
    thread = Thread(target=lambda: result.update(value=func()), context=copy_context())
    thread.start()
    thread.join()
    return result['value']


def _in_pool(pool: ThreadPoolExecutor, func):
    return pool.submit(copy_context().run, func).result()


def _endpoint():
    return ssm.meta.endpoint_url


def test__shared_kwargs_set_in_one_thread__reach_clients_made_in_other_threads():
    BotoClients.Ssm.SharedKwargs.grab().boto_kwargs = {'endpoint_url': 'http://localhost:4566'}

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert _in_pool(pool, _endpoint) == 'http://localhost:4566'
    assert _in_new_thread(_endpoint) == 'http://localhost:4566'
    assert _endpoint() == 'http://localhost:4566'


def test__clients_are_still_made_per_thread():
    def client():
        return BotoClients.Ssm.grab().boto_client

    assert _in_new_thread(client) is not client()


def test__changing_shared_kwargs__makes_clients_again_in_every_thread():
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert _in_pool(pool, _endpoint) == DEFAULT_ENDPOINT
        assert _endpoint() == DEFAULT_ENDPOINT

        BotoClients.Ssm.SharedKwargs.grab().boto_kwargs = {'endpoint_url': 'http://localhost:4566'}

        assert _in_pool(pool, _endpoint) == 'http://localhost:4566'
        assert _endpoint() == 'http://localhost:4566'


def test__a_clients_own_kwargs__win_over_shared_ones():
    BotoClients.Ssm.SharedKwargs.grab().boto_kwargs = {
        'endpoint_url': 'http://localhost:4566', 'region_name': 'us-west-2',
    }

    with BotoClients.Ssm(endpoint_url='http://localhost:9999'):
        assert _endpoint() == 'http://localhost:9999'
        assert ssm.meta.region_name == 'us-west-2'

    assert _endpoint() == 'http://localhost:4566'


def test__overriding_shared_kwargs__reaches_threads_started_inside_it_and_then_ends():
    with BotoClients.Ssm.SharedKwargs(endpoint_url='http://localhost:4566'):
        assert _endpoint() == 'http://localhost:4566'
        assert _in_new_thread(_endpoint) == 'http://localhost:4566'

    assert _in_new_thread(_endpoint) == DEFAULT_ENDPOINT
    assert _endpoint() == DEFAULT_ENDPOINT


def test__each_kind_of_client__has_its_own_shared_kwargs():
    BotoClients.Ssm.SharedKwargs.grab().boto_kwargs = {'endpoint_url': 'http://localhost:4566'}

    assert BotoClients.S3.SharedKwargs is not BotoClients.Ssm.SharedKwargs
    assert BotoClients.S3.SharedKwargs.grab().boto_kwargs == {}
