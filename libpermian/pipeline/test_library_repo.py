import unittest
from unittest.mock import patch
import shutil
import os
import re
import subprocess

from .library_repo import clone, branchname_strategy
from ..events.base import Event
from ..settings import Settings
from ..exceptions import LibraryNotFound

def make_git_testrepo(src_directory):
    """
    Take ``src_directory`` and make a git repository from it.
    Take all subdirectories and consider them as branches. The directory can
    start with ``XX-`` prefix where ``XX`` is number and this will be dropped
    from the branch name. The numbers are used to mimic order of commits in the
    branches.

    A new directory is created named based on the ``src_directory`` replacing
    trailing ``.src`` with ``.git`` and path to this new directory which is
    a git repositry is returned.
    """
    numprefix = re.compile('^([0-9]+-)?')
    git_directory = re.sub(r'\.src$', '.git', src_directory)
    os.mkdir(git_directory)
    subprocess.run(['git', 'init', '-q'], cwd=git_directory, check=True)
    for srcbranchdir in sorted(os.listdir(src_directory)):
        branch = numprefix.sub('', srcbranchdir)
        subprocess.run(['git', 'checkout', '-q', '-b', branch], cwd=git_directory, check=True)
        subprocess.run(['cp', '-rT', os.path.join(src_directory, srcbranchdir), git_directory], check=True)
        files = os.listdir(git_directory)
        subprocess.run(['git', 'add'] + files, cwd=git_directory, check=True)
        message = f"Create branch {branch}"
        subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', message], cwd=git_directory, check=True) # use --allow-empty to make commit even if there are no changes
    return git_directory

def mocked_strategy(*args, **kwargs):
    yield 'PRODUCT-MAJOR.MINOR.FOO.BAR-BAZ'
    yield 'PRODUCT-MAJOR.MINOR.FOO.BAR'
    yield 'PRODUCT-MAJOR.MINOR.FOO'
    yield 'PRODUCT-MAJOR.MINOR'
    yield 'PRODUCT-MAJOR'
    yield 'PRODUCT'

def mocked_strategy_selector(name):
    return mocked_strategy

class TestBranchnameStrategy(unittest.TestCase):
    def setUp(self):
        self.overrides = {
            'library' : {}
        }

    def test_exact_match(self):
        for branchName in ['123', 'xyz']:
            with self.subTest(branchName=branchName):
                self.overrides['library'].update({
                    'branchNameStrategy': 'exact-match',
                    'branchNameFormat': branchName,
                })
                self.assertEqual(
                    list(branchname_strategy('exact-match')(Event(None, 'test'), Settings(self.overrides, {}, []))),
                    [branchName]
                )

    def test_drop_least_significant(self):
        self.overrides['library'].update({
            'branchNameStrategy': 'drop-least-significant',
            'branchNameFormat': 'Fo0-1.2a.3-4b-5.6c',
        })
        self.assertEqual(
            list(branchname_strategy('drop-least-significant')(Event(None, 'test'), Settings(self.overrides, {}, []))),
            [
                'Fo0-1.2a.3-4b-5.6c',
                'Fo0-1.2a.3-4b-5',
                'Fo0-1.2a.3-4b',
                'Fo0-1.2a.3',
                'Fo0-1.2a',
                'Fo0-1',
                'Fo0',
            ]
        )

class TestCloneLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.testrepo = make_git_testrepo('./tests/repos/test_clone.src')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.testrepo)

    def setUp(self):
        self.overrides = {
            'library' : {'repoURL' : os.path.abspath(self.testrepo)}
        }
        self.cloned = None

    def tearDown(self):
        if self.cloned is not None:
            shutil.rmtree(self.cloned)

    def clone_library(self, *args, **kwargs):
        self.cloned = clone(*args, **kwargs)

    def assertBranch(self, branchName):
        self.assertIsNotNone(self.cloned)
        branch = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=self.cloned, stdout=subprocess.PIPE, check=True).stdout[:-1] # drop trailing newline
        self.assertEqual(branch, branchName.encode())

    def test_exact_match(self):
        self.overrides['library'].update({
            'branchNameStrategy': 'exact-match',
            'branchNameFormat': 'PRODUCT',
        })
        event = Event(None, 'test')
        self.clone_library(None, event, Settings(self.overrides, {}, []))
        self.assertBranch("PRODUCT")

    def test_nonexistent_branch(self):
        self.overrides['library'].update({
            'branchNameStrategy': 'exact-match',
            'branchNameFormat': 'nonexistent',
        })
        event = Event(None, 'test')
        with self.assertRaises(LibraryNotFound):
            self.clone_library(None, event, Settings(self.overrides, {}, []))

    def test_nonexistent_repo(self):
        self.overrides['library'].update({
            'branchNameStrategy': 'exact-match',
            'branchNameFormat': 'PRODUCT',
            'repoURL': '/does/not/exist',
        })
        event = Event(None, 'test')
        with self.assertRaises(LibraryNotFound):
            self.clone_library(None, event, Settings(self.overrides, {}, []))

    @patch('libpermian.pipeline.library_repo.branchname_strategy', new=mocked_strategy_selector)
    def test_first_branch_is_used(self):
        event = Event(None, 'test')
        self.clone_library(None, event, Settings(self.overrides, {}, []))
        self.assertBranch("PRODUCT-MAJOR.MINOR.FOO")
