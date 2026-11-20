import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_resources_oss import digest_file, resources


class ResourceManifestTests(unittest.TestCase):
    def test_files_hashes_empty_directories_and_symlinks_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'outputs/empty').mkdir(parents=True)
            payload=b'archival data\n'
            (root/'outputs/source.bin').write_bytes(payload)
            (root/'outputs/source-link').symlink_to('source.bin')
            (root/'outputs/.DS_Store').write_bytes(b'ignored metadata')
            entries={row['path']:row for row in resources(root)}
            self.assertEqual(entries['outputs/source.bin']['sha256'],hashlib.sha256(payload).hexdigest())
            self.assertEqual(entries['outputs/source-link']['target'],'source.bin')
            self.assertEqual(entries['outputs/empty']['type'],'directory')
            self.assertNotIn('outputs/.DS_Store',entries)

    def test_symlinked_directories_are_not_followed_outside_resource_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'outputs').mkdir()
            (root/'not-archived').mkdir()
            (root/'not-archived/private.txt').write_text('outside requested resource paths')
            (root/'outputs/shortcut').symlink_to(root/'not-archived',target_is_directory=True)
            entries={row['path']:row for row in resources(root)}
            self.assertEqual(entries['outputs/shortcut']['type'],'symlink')
            self.assertNotIn('outputs/shortcut/private.txt',entries)

    def test_digest_is_streamed_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source'
            path.write_bytes(b'unchanged')
            before=path.stat().st_mtime_ns
            self.assertEqual(digest_file(path),hashlib.sha256(b'unchanged').hexdigest())
            self.assertEqual(path.stat().st_mtime_ns,before)
