import os
import platform
import pytest
import settings


@pytest.mark.fail_test
def fail_test(request):
    """ This is a fail
    Scenario:
    """
    raise Exception("Test failed!")
