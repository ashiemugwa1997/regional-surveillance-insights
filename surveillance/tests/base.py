from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class LoadedDataTestCase(TestCase):
    """Base case that runs the real ETL once into the test database."""

    @classmethod
    def setUpTestData(cls):
        # Run the actual load_data command so tests exercise the real pipeline.
        call_command("load_data", stdout=StringIO(), stderr=StringIO())
