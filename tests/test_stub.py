import os
import platform
import pytest
import settings


@pytest.mark.test_stub
def test_stub(request):
    """ This is a stub test
    Scenario:
    """
    print("The test: ", request.node.name)
