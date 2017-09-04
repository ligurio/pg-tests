import pytest


@pytest.mark.minor_updates
class TestMinorUpdates():

    @pytest.mark.parametrize("create_environment", [1], indirect=True)
    @pytest.mark.usefixtures('install_postgres')
    def test_minor_updates(self, install_postgres):
        pass


@pytest.mark.major_updates
class TestMajorUpdates():
    """ Test class for majos updates

    """
    versions_from_upgrade = []
    versions_to_upgrade = []
    #
    #
    # @pytest.mark.usefixture("create_environment")
    # @pytest.mark.parametrize("from_update, to_update", [("9.5", "9.6"), ("9.6", "10")], indirect=True)
    # def test_major_update(self, from_update, to_update):
    #     print("Hi")
    #
    # @pytest.mark.usefixture("create_environment")
    # @pytest.mark.parametrize("from_update, to_update", [(["9.5", "ee"]), (["9.6", "standard"]), ("9.6", "10")],
    #                          indirect=True)
    # def test_major_migration(self, from_update, to_update):
    #     print("Bye")
