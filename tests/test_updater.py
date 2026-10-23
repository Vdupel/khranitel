"""Ключи обновления и exit-код watchdog."""

import unittest

from khranitel import updater


class UpdaterConstantsTests(unittest.TestCase):
    def test_restart_exit_code(self):
        self.assertEqual(updater.RESTART_EXIT_CODE, 75)

    def test_git_available_in_this_repo(self):
        self.assertTrue(updater.git_available())


if __name__ == "__main__":
    unittest.main()
