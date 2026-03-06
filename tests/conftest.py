import pytest
import moto
import os

# Ensure we don't have any real keys/id's; just in case.
os.environ['AWS_ACCESS_KEY_ID'] = ''
os.environ['AWS_SECRET_ACCESS_KEY'] = ''
os.environ['AWS_SESSION_TOKEN'] = ''
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


@pytest.fixture(autouse=True)
def mock_aws_fixture():
    with moto.mock_aws():
        yield

