from xboto.dependencies import (
    boto_clients, boto_resources, BotoResources, BotoClients, BotoSession
)
from xboto.client import ssm
from xboto.resource import dynamodb
import moto
from xboto.dependencies import boto_session


def test_client_property():
    a = boto_clients.ssm
    b = boto_clients.ssm
    assert a == b


def test_client_attr():
    a = boto_clients.s3
    b = boto_clients.s3
    assert a == b


def test_resource_attr():
    a = boto_resources.ec2
    b = boto_resources.ec2
    assert a == b
    # Try a third-lookup
    assert a == boto_resources.ec2


def test_internal_cache_per_instance():
    # Ensure the two types don't insert things into each others
    # internal list of cached lazy boto clients/resources
    r = BotoResources()
    c = BotoClients()
    assert c.dynamodb is not r.dynamodb

    c_dynamodb = c.dynamodb
    r_dynamodb = r.dynamodb

    # We return same client/resource each time we ask for it
    assert c.dynamodb is c_dynamodb
    assert r.dynamodb is r_dynamodb

    # With a new BotoSession, we should get back new clients/resources.
    with BotoSession():
        assert c.dynamodb is not c_dynamodb
        assert r.dynamodb is not r_dynamodb

    # We should again return same client/resource each time we ask for it
    assert c.dynamodb is c_dynamodb
    assert r.dynamodb is r_dynamodb


def test_clients_ssm_importable():
    # Let's try using the `ssm` client imported from the `clients` module.
    path = f"/some-service/test_name"

    # Put some test-data in ssm
    ssm.put_parameter(Name=path, Value="testValue2", Type="String")

    # Make sure client is working....
    v = ssm.get_parameter(Name=path)
    assert v["Parameter"]["Value"] == "testValue2"


def test_resources_dynamodb_importable():
    table = dynamodb.create_table(
        TableName="test_table",
        KeySchema=[
            # Partition Key
            {"AttributeName": "name", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "name", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
        SSESpecification={"Enabled": True},
    )

    assert table.table_status == "ACTIVE"


@BotoSession(region_name='us-west-23', reset_session_when_activated=True)
def test_boto_session_overridable():

    # See if the boto-session we are using has its region set to 'us-west-23':
    assert boto_session.session.region_name == 'us-west-23'

    # Dynamo resource should use the boto-session, and should now be using the new region:
    dyn_client = dynamodb.meta.client
    assert dyn_client.meta.region_name == 'us-west-23'
    assert dyn_client.meta.endpoint_url == 'https://dynamodb.us-west-23.amazonaws.com'


def test_change_boto_kwargs_on_existing():
    assert dynamodb.meta.client.meta.endpoint_url == "https://dynamodb.us-east-1.amazonaws.com"

    set_with_boto_kwargs = {
        'region_name': 'us-west-5'
    }

    BotoResources.DynamoDB.grab().boto_kwargs = set_with_boto_kwargs

    assert dynamodb.meta.client.meta.endpoint_url == "https://dynamodb.us-west-5.amazonaws.com"

    current_boto_kwargs = BotoResources.DynamoDB.grab().boto_kwargs

    # Make sure they equal but are NOT the same exact dict (should be a copy)
    assert current_boto_kwargs == set_with_boto_kwargs
    assert current_boto_kwargs is not set_with_boto_kwargs


def test_get_lambda_client():
    from xboto import BotoClients
    BotoClients.grab().load('lambda_')

