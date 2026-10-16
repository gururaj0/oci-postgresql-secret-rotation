import importlib.util
from types import SimpleNamespace
import unittest


@unittest.skipUnless(importlib.util.find_spec("oci"), "OCI SDK required for discovery adapter")
class PaginationTests(unittest.TestCase):
    def test_collection_and_list_pages(self):
        from discovery.client import all_results
        calls = []

        def listing(**kwargs):
            calls.append(kwargs)
            if "page" not in kwargs:
                return SimpleNamespace(data=SimpleNamespace(items=[1, 2]), headers={"opc-next-page": "next"})
            return SimpleNamespace(data=[3], headers={})

        self.assertEqual(all_results(listing), [1, 2, 3])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["page"], "next")

    def test_failure_is_returned_without_helper_retry(self):
        from discovery.client import all_results
        calls = []

        def listing(**kwargs):
            calls.append(kwargs)
            raise TimeoutError

        with self.assertRaises(TimeoutError):
            all_results(listing)
        self.assertEqual(len(calls), 1)
