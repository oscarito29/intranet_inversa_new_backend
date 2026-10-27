from django.apps import apps
from django.test.runner import DiscoverRunner


class ManagedModelTestRunner(DiscoverRunner):
    """
    Las tablas del sistema anterior son `managed = False`: Django no las crea. Para los
    tests (SQLite en memoria) se activa `managed = True` mientras dura la ejecución.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._no_gestionados = [modelo for modelo in apps.get_models() if not modelo._meta.managed]
        for modelo in self._no_gestionados:
            modelo._meta.managed = True

    def teardown_test_environment(self, **kwargs):
        for modelo in self._no_gestionados:
            modelo._meta.managed = False
        super().teardown_test_environment(**kwargs)
