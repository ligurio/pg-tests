import os
import platform
import pytest


def fail_test(request):
    """ This is a fail
    Scenario:
    """
    raise Exception("Test failed!")
