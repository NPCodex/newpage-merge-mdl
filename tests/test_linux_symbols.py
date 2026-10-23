import unittest
from linux_package_smoke import check_symbol_versions


class SymbolContract(unittest.TestCase):
    limits = {'GLIBC': '2.39', 'GLIBCXX': '3.4.32', 'CXXABI': '1.3.15'}

    def test_supported_and_static(self):
        actual = check_symbol_versions('tool', 'Name: GLIBC_2.2.5 Name: GLIBC_2.39 Name: GLIBCXX_3.4.32', self.limits)
        self.assertEqual(actual['GLIBC'], '2.39')
        self.assertIsNone(actual['CXXABI'])
        self.assertTrue(all(v is None for v in check_symbol_versions('static', '', self.limits).values()))

    def test_newer_or_private_symbols_fail(self):
        for text in ('GLIBC_2.40', 'GLIBCXX_3.4.33', 'CXXABI_1.3.16', 'GLIBC_PRIVATE'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_symbol_versions('tool', text, self.limits)


if __name__ == '__main__':
    unittest.main()
