

Provide an easy way to get a lazy, shared, thread-safe boto3 client/resource.


<!-- markdownlint-disable -->
--8<-- "README.md"


## Benefits

Here are some of the benefits:

- Lazily created, so we only create the ones that are needed on-demand.
  - Allows code to use `moto` more easily (boto/aws mocking), as `moto` needs the client/resource
    to be created after unit-test starts.
- The boto client/resources are shared when code runs on the same thread.
  - This allows reusing already open connections to their services (such as dynamodb, ssm, etc).
- Guaranteed to get a shared client/resource for each thread.
  - Using xyn-aws will allow you to easily use boto3 in a thread-safe manner.
- They are cleaned-up/thrown-away between each unit test run.
  - xyn-aws uses xyn-resource to help it clean-up and share the boto resources/clients.
  - Clients/Resources are all automatically cleared out at start of unit-test.
  - Then they are re-created lazily, as needed, during each unit test function run (as with any xyn-resource).

## How To Use

There are two main ways to use this library.

You can import the lazily boto3 client/resource like so:

```python
from xboto.client import ssm

def some_function():
    # You can use it just like the normal boto3 ssm client.
    # Call the standard ssm client `get_paginator` method:
    my_paginator = ssm.get_paginator(...)
```

In this example above, every time you use `ssm`, it will lazily lookup the current shared ssm
client for the current thread. If it does not exist yet, it will create the client for you.

The same thing exists for boto3 resources:

```python
from xboto.resource import dynamodb

def some_function():
    # You can use it just like the normal boto3 dynamodb resource.
    # Create the standard dynamodb resource `Table` object:
    my_table = dynamodb.Table('my-table-name')
```

There are type-hints on these modules for common clients we use,
but you can import anything boto supports even if there is not type-hint defined for it (yet).

If you do end up importing something boto does not support, you'll only get an error when you first
attempt to use the imported client. This is because we don't attempt to create the client until
the first time it's used.

The other way you can get a boto client/resource is though a special proxy object.
With this proxy object, you can ask it for any standard boto3 client:

```python
# Simply import and use it as-if it's a ready-to-go client.
# (you can use `xboto.client` for clients)
from xboto import boto_clients

def some_func():
    # You can use it just like the normal boto3 ssm client.
    # Every time you use it, it will lazily lookup the current one for the current thread.
    ssm_paginator = boto_clients.ssm.get_paginator('get_parameters_by_path')
```

Or any standard boto3 resource:

```python
from xboto import boto_resources

def some_func():
    my_table = boto_resources.dynamodb.Table('my-table-name')
```

You can also get them directly from the top-level module with a
less-verbose name:

```python
import xboto

def some_func():
    my_table = xboto.resource.dynamodb.Table('my-table-name')
    my_ssm = xboto.client.ssm.get_object('/some-key')
```

Finally, you can also import these and directly use them:

```python
# Client won't actually be created until it's actually used
# for the first time (lazily)
from xboto.resource import dynamodb
from xboto.client import ssm

def some_func():
    # Client is created the first time here (first use)
    # It did not happen when they were imported.
    
    my_table = dynamodb.Table('my-table-name')
    my_ssm = ssm.get_object('/some-key')
```

## Settings for every thread

Each thread gets its own client or resource. To create all of them with the same settings, such as
an `endpoint_url`, set them on the client's `SharedKwargs`. It is shared by every thread:

```python
from xboto import BotoClients

BotoClients.ApiGatewayManagementApi.SharedKwargs.grab().boto_kwargs = {
    'endpoint_url': 'https://wsapi.example.com',
}
```

Every client made after this, in any thread, uses that endpoint. A client made earlier is made
again the next time it's used.

To use different settings for a while:

```python
from xboto import BotoResources

with BotoResources.DynamoDB.SharedKwargs(endpoint_url='http://localhost:8000'):
    ...
```

Kwargs given to a client or resource directly, like `BotoClients.Ssm(region_name='us-west-2')`,
are used on top of the shared ones. Between unit tests, the shared kwargs are cleared.

## Configuration (Deprecated)

To change the endpoint_url used when boto3 creates a new client or resource,
set the settings file to the value desired.  This will be used in:

In your project `conf.py`:

```python
from xyn_config import ConfigSettings, config
from xboto.conf import Boto3Settings


class MyProjectSettings(ConfigSettings):
    boto3_endpoint_url: str = "http://endpoint_url"

Boto3Settings.endpoint_url = MyProjectSettings.boto3_endpoint_url
```

This would allow you to change by an environment variable for local dynamodb, for example.

`.env`:

```ini
BOTO3_ENDPOINT_URL=http://localhost:55000
```

```python
boto3.client('awsservice', endpoint_url=VALUE_FROM_CONF)
boto3.resource('awsresource', endpoint_url=VALUE_FROM_CONF)
```
