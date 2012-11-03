import unittest2 as unittest
from fabric.api import run

import sys

from parcel.distro import debian
from parcel.deploy import Deployment


class TestDeploy(Deployment):
    """Simple test class for deploytment which  overrides __init__ so we are not calling remote host"""
    def __init__(self, app_name=None):
        self.app_name = app_name


class DistroTestSuite(unittest.TestCase):
    """Versions test cases."""

    def setUp(self):
        self.saved_side_effect = run.side_effect
        run.reset_mock()
        
    def tearDown(self):
        run.reset_mock()
        
        #restore default side_effect
        run.side_effect = self.saved_side_effect

    def test_update_packages(self):
        debian.update_packages()
        run.assert_called_once_with("apt-get update -qq")
        
    def test_cleanup(self):
        debian._cleanup()
        self.assertEqual(run.call_count,1)
        self.assertTrue("rm -rf" in run.call_args[0][0])

    def test_setup(self):
        debian._setup()
        commands = run.call_args_list                   # get the commands run remotely in order
        
        # clean command should top list
        self.assertTrue("rm -rf" in commands[0][0][0])
        
        # the rest should be mkdirs.
        for command in commands[1:]:
            self.assertTrue(command[0][0].startswith('mkdir '))
            
            # the classes build space should be in the path
            self.assertTrue(debian.space in command[0][0])
        
    def test_check_fpm_not_present(self):
        def called(command):
            class retobj: pass
            retval = retobj()
            
            if 'fpm' in command:
                retval.return_code = 1
            elif 'checkinstall' in command:
                retval.return_code = 0
        
            return retval 
            
        run.side_effect = called              # return these two objects from two calls to run
        self.assertRaises(Exception,debian.check,())                  # should be fpm exception
        
    def test_check_fpm_present_checkinstall_not(self):
        def called(command):
            class retobj: pass
            retval = retobj()
            
            if 'fpm' in command:
                retval.return_code = 0
            elif 'checkinstall' in command:
                retval.return_code = 1
        
            return retval 
            
        run.side_effect = called              # return these two objects from two calls to run
        
        self.assertRaises(Exception,debian.check,())                  # should be checkinstall exception
        
    def test_check_everything_present(self):
        class retobj: pass
        retval = retobj()
        retval.return_code = 0
            
        run.return_value = retval              # return these two objects from two calls to run
        
        debian.check()
        
    
    def test_write_prerm_template(self):

        # override __init__ so we are not calling remote host
        class TestDeploy(Deployment):
            def __init__(self, app_name=None):
                self.app_name = app_name

        prerm_template = "Test rm template {app_name} and {lines}"

        # test with no prerm lines
        app_name = "testapp"
        lines = []
        d = TestDeploy(app_name=app_name)
        d.write_prerm_template(prerm_template)
        self.assertEquals(d.prerm, prerm_template.format(app_name=app_name, lines="\n        ".join(lines)))

        # test with prerm lines
        app_name = "testapp"
        lines = ["test line 1", "test line 2"]
        d = TestDeploy(app_name=app_name)
        d.add_prerm(lines)
        d.write_prerm_template(prerm_template)
        self.assertEquals(d.prerm, prerm_template.format(app_name=app_name, lines="\n        ".join(lines)))


    def test_write_postinst_template(self):

        postinst_template = "Test postint template {app_name} and {lines}"

        # test with no postinst lines
        app_name = "testapp"
        lines = []
        d = TestDeploy(app_name=app_name)
        d.write_postinst_template(postinst_template)
        self.assertEquals(d.postinst, postinst_template.format(app_name=app_name, lines="\n        ".join(lines)))

        # test with postinst lines
        app_name = "testapp"
        lines = ["test line 1", "test line 2"]
        d = TestDeploy(app_name=app_name)
        d.add_postinst(lines)
        d.write_postinst_template(postinst_template)
        self.assertEquals(d.postinst, postinst_template.format(app_name=app_name, lines="\n        ".join(lines)))
