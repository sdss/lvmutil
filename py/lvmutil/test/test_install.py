# Licensed under a 3-clause BSD style license - see LICENSE.rst
# -*- coding: utf-8 -*-
"""Test lvmutil.install.
"""
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
# The line above will help with 2to3 support.
import unittest
from os import chdir, environ, getcwd, mkdir, remove, rmdir
from os.path import dirname, isdir, join
from shutil import rmtree
from argparse import Namespace
from tempfile import mkdtemp
from logging import getLogger
from pkg_resources import resource_filename
from ..log import DEBUG
from ..install import DesiInstall, DesiInstallException, dependencies
from .test_log import TestHandler


skipMock = False
try:
    from unittest.mock import patch
except ImportError:
    # Python 2
    skipMock = True


class TestInstall(unittest.TestCase):
    """Test lvmutil.install.
    """

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        # Create a "fresh" DesiInstall object for every test.
        self.desiInstall = DesiInstall()
        # Replace the log handler with something that writes to memory.
        root_logger = getLogger(self.desiInstall.log.name.rsplit('.', 1)[0])
        while len(root_logger.handlers) > 0:
            h = root_logger.handlers[0]
            fmt = h.formatter
            root_logger.removeHandler(h)
        mh = TestHandler()
        mh.setFormatter(fmt)
        root_logger.addHandler(mh)
        self.desiInstall.log.setLevel(DEBUG)
        # Create a temporary directory.
        self.data_dir = mkdtemp()

    def tearDown(self):
        rmtree(self.data_dir)

    def assertLog(self, order=-1, message=''):
        """Examine the log messages.
        """
        handler = getLogger(self.desiInstall.log.name.rsplit('.', 1)[0]).handlers[0]
        record = handler.buffer[order]
        self.assertEqual(record.getMessage(), message)

    @unittest.skipIf(skipMock, "Skipping test that requires unittest.mock.")
    def test_dependencies(self):
        """Test dependency processing.
        """
        # Raise ValueError if file doesn't exist:
        with self.assertRaises(ValueError) as cm:
            dependencies("foo/bar/baz.module")
        self.assertEqual(str(cm.exception),
                         "Modulefile foo/bar/baz.module does not exist!")
        # Manipulate the environment.
        with patch.dict('os.environ', {'NERSC_HOST': 'FAKE'}):
            # NERSC dependencies.
            deps = dependencies(resource_filename('lvmutil.test',
                                                  't/nersc_dependencies.txt'))
            self.assertEqual(set(deps),
                             set(['astropy-hpcp', 'setuptools-hpcp',
                                  'lvmutil/1.0.0']))
            # Standard dependencies.
            del environ['NERSC_HOST']
            deps = dependencies(resource_filename('lvmutil.test',
                                                  't/generic_dependencies.txt'))
            self.assertEqual(set(deps), set(['astropy', 'lvmutil/1.0.0']))

    @unittest.skipIf(skipMock, "Skipping test that requires unittest.mock.")
    def test_get_options(self):
        """Test the processing of desiInstall command-line arguments.
        """
        # Set a few environment variables for testing purposes.
        with patch.dict('os.environ', {'MODULESHOME': '/fake/module/directory',
                                       'LVM_PRODUCT_ROOT': '/fake/desi/directory'}):
            default_namespace = Namespace(
                anaconda=self.desiInstall.anaconda_version(),
                bootstrap=False,
                config_file='',
                cross_install=False,
                default=False,
                force=False,
                force_build_type=False,
                keep=False,
                knl=False,
                moduledir=u'',
                moduleshome='/fake/module/directory',
                product=u'NO PACKAGE',
                product_version=u'NO VERSION',
                root='/fake/desi/directory',
                test=False,
                username=environ['USER'],
                verbose=False)
            options = self.desiInstall.get_options([])
            self.assertEqual(options, default_namespace)
            default_namespace.product = 'product'
            default_namespace.product_version = 'version'
            options = self.desiInstall.get_options(['product', 'version'])
            self.assertEqual(options, default_namespace)
            default_namespace.default = True
            options = self.desiInstall.get_options(['-d', 'product', 'version'])
            self.assertEqual(options, default_namespace)
            #
            # Examine the log.
            #
            default_namespace.default = False
            default_namespace.verbose = True
            options = self.desiInstall.get_options(['-v', 'product', 'version'])
            self.assertTrue(self.desiInstall.options.verbose)
            self.assertLog(order=-1, message="Set log level to DEBUG.")
            self.assertLog(order=-2,
                           message="Called parse_args() with: -v product version")
        # Test missing environment:
        with patch.dict('os.environ', {'MODULESHOME': '/fake/module/directory'}):
            if 'LVM_PRODUCT_ROOT' in environ:
                del environ['LVM_PRODUCT_ROOT']
            options = self.desiInstall.get_options(['-v', 'product', 'version'])
            default_namespace.root = None
            self.assertEqual(options, default_namespace)
        # self.assertIn('LVM_PRODUCT_ROOT', environ)

    @unittest.skipIf(skipMock, "Skipping test that requires unittest.mock.")
    def test_sanity_check(self):
        """Test the validation of command-line options.
        """
        options = self.desiInstall.get_options([])
        with self.assertRaises(DesiInstallException) as cm:
            self.desiInstall.sanity_check()
        self.assertEqual(str(cm.exception),
                         "You must specify a product and a version!")
        with patch.dict('os.environ', {'MODULESHOME': self.data_dir}):
            options = self.desiInstall.get_options(['-b'])
            self.desiInstall.sanity_check()
            self.assertTrue(options.bootstrap)
            self.assertEqual(options.product, 'lvmutil')
            del environ['MODULESHOME']
            options = self.desiInstall.get_options(['-b'])
            with self.assertRaises(DesiInstallException) as cm:
                self.desiInstall.sanity_check()
            self.assertEqual(str(cm.exception),
                             "You do not appear to have Modules set up.")

    def test_get_product_version(self):
        """Test resolution of product/version input.
        """
        ini = resource_filename('lvmutil.test',
                                't/desiInstall_configuration.ini')
        options = self.desiInstall.get_options(['foo', 'bar'])
        out = self.desiInstall.get_product_version()
        self.assertEqual(out, (u'https://github.com/desihub/foo',
                         'foo', 'bar'))
        options = self.desiInstall.get_options(['lvmutil', '1.0.0'])
        out = self.desiInstall.get_product_version()
        self.assertEqual(out, (u'https://github.com/desihub/lvmutil',
                         'lvmutil', '1.0.0'))
        options = self.desiInstall.get_options(['desihub/desispec', '2.0.0'])
        out = self.desiInstall.get_product_version()
        self.assertEqual(out, (u'https://github.com/desihub/desispec',
                         'desispec', '2.0.0'))
        options = self.desiInstall.get_options(['--configuration',
                                                ini, 'my_new_product', '1.2.3'])
        out = self.desiInstall.get_product_version()
        self.assertEqual(out, (u'https://github.com/me/my_new_product',
                         'my_new_product', '1.2.3'))
        # Reset the config attribute after testing.
        self.desiInstall.config = None

    def test_identify_branch(self):
        """Test identification of branch installs.
        """
        options = self.desiInstall.get_options(['lvmutil', '1.0.0'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.assertEqual(url,
                         ('https://github.com/desihub/lvmutil/archive/' +
                          '1.0.0.tar.gz'))
        options = self.desiInstall.get_options(['lvmutil', 'master'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.assertEqual(url,
                         'https://github.com/desihub/lvmutil.git')
        options = self.desiInstall.get_options(['desiAdmin', '1.0.0'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.assertEqual(url,
                         ('https://desi.lbl.gov/svn/code/tools/desiAdmin/' +
                          'tags/1.0.0'))
        options = self.desiInstall.get_options(['desiAdmin', 'trunk'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.assertEqual(url,
                         'https://desi.lbl.gov/svn/code/tools/desiAdmin/trunk')
        options = self.desiInstall.get_options(['desiAdmin',
                                                'branches/testing'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.assertEqual(url,
                         ('https://desi.lbl.gov/svn/code/tools/desiAdmin/' +
                          'branches/testing'))

    def test_verify_url(self):
        """Test the check for a valid svn URL.
        """
        options = self.desiInstall.get_options(['-v', 'desispec', '0.1'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.assertTrue(self.desiInstall.verify_url())
        self.desiInstall.product_url = 'http://desi.lbl.gov/no/such/place'
        with self.assertRaises(DesiInstallException) as cm:
            self.desiInstall.verify_url()
        message = ("Error {0:d} querying GitHub URL: {1}.".format(
                   404, self.desiInstall.product_url))
        self.assertEqual(str(cm.exception), message)
        options = self.desiInstall.get_options(['-v', 'desiAdmin', 'trunk'])
        out = self.desiInstall.get_product_version()
        url = self.desiInstall.identify_branch()
        self.desiInstall.verify_url(svn='echo')
        message = ' '.join(['--non-interactive', '--username',
                           self.desiInstall.options.username,
                           'ls', self.desiInstall.product_url]) + "\n"
        self.assertLog(-1, message=message)
        with self.assertRaises(DesiInstallException):
            self.desiInstall.verify_url(svn='which')

    def test_build_type(self):
        """Test the determination of the build type.
        """
        options = self.desiInstall.get_options([])
        if hasattr(self.desiInstall, 'working_dir'):
            old_working_dir = self.desiInstall.working_dir
        else:
            old_working_dir = None
        self.desiInstall.working_dir = self.data_dir
        self.assertEqual(self.desiInstall.working_dir, self.data_dir)
        options = self.desiInstall.get_options(['desispec', '1.0.0'])
        self.assertEqual(self.desiInstall.build_type, set(['plain']))
        options = self.desiInstall.get_options(['-C', 'desispec', '1.0.0'])
        self.assertEqual(self.desiInstall.build_type, set(['plain', 'make']))
        # Create temporary files
        options = self.desiInstall.get_options(['desispec', '1.0.0'])
        tempfiles = {'Makefile': 'make', 'setup.py': 'py'}
        for t in tempfiles:
            tempfile = join(self.data_dir, t)
            with open(tempfile, 'w') as tf:
                tf.write('Temporary file.\n')
            self.assertEqual(self.desiInstall.build_type,
                             set(['plain', tempfiles[t]]))
            remove(tempfile)
        # Create temporary directories
        tempdirs = {'src': 'src'}
        for t in tempdirs:
            tempdir = join(self.data_dir, t)
            mkdir(tempdir)
            self.assertEqual(self.desiInstall.build_type,
                             set(['plain', tempdirs[t]]))
            rmdir(tempdir)
        if old_working_dir is None:
            del self.desiInstall.working_dir
        else:
            self.desiInstall.working_dir = old_working_dir

    @unittest.skipIf(skipMock, "Skipping test that requires unittest.mock.")
    def test_anaconda_version(self):
        """Test determination of the DESI+Anaconda version.
        """
        with patch.dict('os.environ', {'DESICONDA': 'FOO'}):
            v = self.desiInstall.anaconda_version()
            self.assertEqual(v, 'current')
            environ['DESICONDA'] = '/global/common/software/desi/cori/desiconda/20170613-1.1.4-spectro/code/desiconda/20170613-1.1.4-spectro_conda'
            v = self.desiInstall.anaconda_version()
            self.assertEqual(v, '20170613-1.1.4-spectro')
            environ['DESICONDA'] = '/global/common/software/desi/cori/desiconda/20170613-1.1.4-spectro/CODE/desiconda/20170613-1.1.4-spectro_conda'
            v = self.desiInstall.anaconda_version()
            self.assertEqual(v, 'current')

    def test_knl(self):
        """Test the knl property.
        """
        options = self.desiInstall.get_options(['lvmutil', 'master'])
        self.assertEqual(self.desiInstall.knl, '')
        options = self.desiInstall.get_options(['--knl', 'lvmutil', 'master'])
        self.assertEqual(self.desiInstall.knl, 'knl')

    def test_default_nersc_dir(self):
        """Test determination of the NERSC installation root.
        """
        options = self.desiInstall.get_options(['lvmutil', 'master'])
        self.desiInstall.nersc = 'edison'
        nersc_dir = self.desiInstall.default_nersc_dir()
        edison_nersc_dir = '/global/common/software/desi/edison/desiconda/current'
        if 'DESICONDA' in environ:
            edison_nersc_dir = edison_nersc_dir.replace('current', self.desiInstall.anaconda_version())
        self.assertEqual(nersc_dir, edison_nersc_dir)
        options = self.desiInstall.get_options(['--anaconda',
                                                'frobulate',
                                                'lvmutil', 'master'])
        self.desiInstall.nersc = 'datatran'
        nersc_dir = self.desiInstall.default_nersc_dir()
        self.assertEqual(nersc_dir, '/global/common/software/desi/datatran/desiconda/frobulate')

    @unittest.skipIf(skipMock, "Skipping test that requires unittest.mock.")
    def test_set_install_dir(self):
        """Test the determination of the install directory.
        """
        with patch.dict('os.environ', {'NERSC_HOST': 'FAKE'}):
            del environ['NERSC_HOST']
            options = self.desiInstall.get_options(['--root',
                                                    '/fake/root/directory',
                                                    'lvmutil', 'master'])
            with self.assertRaises(DesiInstallException):
                install_dir = self.desiInstall.set_install_dir()
            options = self.desiInstall.get_options(['--root', self.data_dir,
                                                    'lvmutil', 'master'])
            self.desiInstall.get_product_version()
            install_dir = self.desiInstall.set_install_dir()
            self.assertEqual(install_dir, join(self.data_dir, 'code', 'lvmutil',
                             'master'))
            # Test for presence of existing directory.
            tmpdir = join(self.data_dir, 'code')
            mkdir(tmpdir)
            mkdir(join(tmpdir, 'lvmutil'))
            mkdir(join(tmpdir, 'lvmutil', 'master'))
            options = self.desiInstall.get_options(['--root', self.data_dir,
                                                    'lvmutil', 'master'])
            self.desiInstall.get_product_version()
            with self.assertRaises(DesiInstallException) as cm:
                install_dir = self.desiInstall.set_install_dir()
            self.assertEqual(str(cm.exception),
                             "Install directory, {0}, already exists!".format(
                             join(tmpdir, 'lvmutil', 'master')))
            options = self.desiInstall.get_options(['--root', self.data_dir,
                                                    '--force', 'lvmutil',
                                                    'master'])
            self.assertTrue(self.desiInstall.options.force)
            self.desiInstall.get_product_version()
            install_dir = self.desiInstall.set_install_dir()
            self.assertFalse(isdir(join(tmpdir, 'lvmutil', 'master')))
            if isdir(tmpdir):
                rmtree(tmpdir)
        # Test NERSC installs.  Unset LVM_PRODUCT_ROOT for this to work.
        with patch.dict('os.environ', {'NERSC_HOST': 'edison', 'LVM_PRODUCT_ROOT': 'FAKE'}):
            del environ['LVM_PRODUCT_ROOT']
            test_code_version = 'test-blat-foo'
            options = self.desiInstall.get_options(['lvmutil', test_code_version])
            self.desiInstall.get_product_version()
            install_dir = self.desiInstall.set_install_dir()
            self.assertEqual(install_dir, join(
                             self.desiInstall.default_nersc_dir(), 'code',
                             'lvmutil', test_code_version))

    @unittest.skipUnless('MODULESHOME' in environ,
                         'Skipping because MODULESHOME is not defined.')
    def test_start_modules(self):
        """Test the initialization of the Modules environment.
        """
        options = self.desiInstall.get_options(['-m',
                                                '/fake/modules/directory',
                                                'lvmutil', 'master'])
        with self.assertRaises(DesiInstallException) as cm:
            status = self.desiInstall.start_modules()
        self.assertEqual(str(cm.exception), ("Could not initialize Modules " +
                         "with MODULESHOME={0}!").format(
                         '/fake/modules/directory'))
        options = self.desiInstall.get_options(['lvmutil', 'master'])
        self.assertEqual(options.moduleshome, environ['MODULESHOME'])
        status = self.desiInstall.start_modules()
        self.assertTrue(callable(self.desiInstall.module))

    def test_nersc_module_dir(self):
        """Test the nersc_module_dir property.
        """
        ini = resource_filename('lvmutil.test',
                                't/desiInstall_configuration.ini')
        self.assertIsNone(self.desiInstall.nersc_module_dir)
        self.desiInstall.nersc = None
        self.assertIsNone(self.desiInstall.nersc_module_dir)
        test_args = ['lvmutil', '1.9.5']
        for knl in (False, True):
            if knl:
                test_args.insert(0, '--knl')
            options = self.desiInstall.get_options(test_args)
            for n in ('edison', 'cori', 'datatran', 'scigate'):
                self.desiInstall.nersc = n
                self.desiInstall.baseproduct = 'lvmutil'
                self.assertEqual(self.desiInstall.nersc_module_dir,
                                 join(self.desiInstall.default_nersc_dir(n),
                                      "modulefiles"))
                self.desiInstall.baseproduct = 'desimodules'
                self.assertEqual(self.desiInstall.nersc_module_dir,
                                 join(self.desiInstall.default_nersc_dir_templates[n].format(knl=('', 'knl')[int(knl)], desiconda_version='startup'),
                                      "modulefiles"))
        options = self.desiInstall.get_options(['--configuration',
                                                ini, 'my_new_product', '1.2.3'])
        self.desiInstall.nersc = 'edison'
        self.assertEqual(self.desiInstall.nersc_module_dir,
                         '/project/projectdirs/desi/test/modules')
        self.desiInstall.nersc = 'cori'
        self.assertEqual(self.desiInstall.nersc_module_dir,
                         '/global/common/cori/contrib/desi/test/modules')

    def test_cleanup(self):
        """Test the cleanup stage of the install.
        """
        options = self.desiInstall.get_options(['lvmutil', 'master'])
        self.desiInstall.original_dir = getcwd()
        self.desiInstall.working_dir = join(self.data_dir, 'lvmutil-master')
        mkdir(self.desiInstall.working_dir)
        chdir(self.desiInstall.working_dir)
        self.desiInstall.cleanup()
        self.assertEqual(getcwd(), self.desiInstall.original_dir)
        self.assertFalse(isdir(self.desiInstall.working_dir))


def test_suite():
    """Allows testing of only this module with the command::

        python setup.py test -m <modulename>
    """
    return unittest.defaultTestLoader.loadTestsFromName(__name__)