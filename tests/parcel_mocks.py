import os
import shutil
import tempfile
from functools import partial

import mock
from fabric.colors import blue
from fabric.api import local, lcd

from parcel.deploy import Deployment
from parcel.versions import Version


# fabric.api
run = mock.MagicMock(name='run')

put = mock.MagicMock(name='put')
cd = lcd
with_settings = mock.MagicMock(name="with_settings")

def mock_put(local_path=None, remote_path=None, use_sudo=False, mirror_local_mode=False, mode=None):
    base_path = os.path.join(os.path.expanduser('~/'), Deployment.build_dir)
    if local_path and remote_path:
        shutil.copy(local_path, os.path.join(base_path, remote_path))

def mock_get(remote_path, local_path=None):
    if remote_path and local_path:
        shutil.copy(remote_path, local_path)

version_run = mock.MagicMock(name="version_run")  # used in test_distro
local = partial(local, capture=True) # this makes local return more like run
def mock_local():
    def func(command):

        # used in test_deploy for test_build_deb
        if command.startswith('fpm') and 'rpm' in command:
            tmpdir = tempfile.mkdtemp()
            test_rpm = os.path.join(os.path.dirname(__file__),"data", "test.rpm")
            rpm = os.path.join(tmpdir, 'testapp_0.1.1-1.noarch.rpm')
            print os.listdir(tmpdir)
            shutil.copy(test_rpm, rpm)
            return 'Created rpm package {{"path":"{0}"}}'.format(rpm)
        elif command.startswith('fpm') and 'deb' in command:
            tmpdir = tempfile.mkdtemp()
            test_deb = os.path.join(os.path.dirname(__file__),"data", "test.deb")
            deb = os.path.join(tmpdir, 'testapp_0.1.2_all.deb')
            shutil.copy(test_deb, deb)
            return 'Created deb package {{"path":"{0}"}}'.format(deb)


        # used in test_deploy to prevent actual pip installs
        if command.startswith('PIP_DOWNLOAD_CACHE'):
            return 'Mocked pip install'

        # used in test_deploy to 'rm' the package that was not created by fpm (because it was mocked)
        if command.startswith("rm '"):
            return 'Mocked rm on deb package.'

        return local(command)
    return func

# fabric.colors
green = mock.MagicMock(name='green')
blue = mock.MagicMock(name='blue')

# fabric.contrib.files
append = mock.MagicMock(name="append")

# parcel.distro
update_packages = mock.MagicMock(name="update_packages")
build_deps =  mock.MagicMock(name="build_deps")

# parcel.versions
version_mock = mock.Mock(spec=Version)
version_mock.return_value = Version("0.1.1")

# rsync
def rsync(sources,dest,rsync_ignore=None,color_files=True):
    if type(sources)==str:
        sources = [sources]

    dest = os.path.join(os.path.expanduser('~/'), dest)
    local('mkdir -p "%s"'%dest)
    data = ''

    for s in sources:
        data += local('cp -R {0} {1}/'.format(s, dest))

    command = []
    command.append('rsync')
    command.append('-av')
    command.extend("'%s'"%s for s in sources)
    command.append("'%s'"%(dest))
                
    if rsync_ignore:
        if os.path.isfile(rsync_ignore):
            command.append('--exclude-from=%s'%rsync_ignore)
    
    if not color_files:   
        return local(" ".join(command))

    print " ".join(command)
        
    data = local(" ".join(command),capture=True)
    lines = data.splitlines()
    lines = lines[1:]
    i=0
    while lines[i]:
        print blue(lines[i])
        i+=1
    for line in lines[i:]:
        print line     

# from fabric code, used to allow arbitrary attribute access
class _AttributeString(str):
    """
    Simple string subclass to allow arbitrary attribute access.
    """
    @property
    def stdout(self):
        return str(self)
