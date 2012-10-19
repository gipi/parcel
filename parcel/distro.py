import os.path

from fabric.api import settings, run, cd, lcd, put, get, local, env, with_settings
from fabric.contrib.files import sed

from . import versions

#
# Used to represent the remote build distribution
#

class Debian(object):
    space = '.parcel-build-temp'

    def __init__(self):
        pass

    def _cleanup(self):
        run("rm -rf '%s'"%self.space)  

    def _setup(self):
        # first cleanup any broken stale previous builds
        self._cleanup()

        # make fresh directories
        base_dir = self.mkdir(self.space)
        src_dir = self.mkdir(self.space+"/src")
        build_dir = self.mkdir(self.space+"/build")
        return base_dir, src_dir, build_dir
        
    @property
    def build_base(self):
        return '/tmp/'
        
    def mkdir(self, remote):
        return run('mkdir "%s" && cd "%s" && pwd'%(remote,remote))

    def update_packages(self):
        with settings(user='root'):
            run("apt-get update -qq")

    def build_deps(self, deps):
        with settings(user='root'):
            run("apt-get install -qq %s"%(' '.join(deps)))

    def version(self,package):
        """Look at the debian apt package system for a package with this name and return its version.
        Return None if there is no such package.
        """
        with settings(warn_only=True):
            vstring = run('apt-cache show %s 2>/dev/null | sed -nr "s/^Version: ([0-9]+)(-.+)?/\\1/p"'%(package))
            if vstring.return_code:
                # error fetching package info. Assume there is no such named package. Return None
                return None
            return versions.Version(vstring)
	
    def push_files(self,pathlist,dst):
        for path in pathlist:
            put(path, dst+"%s"%os.path.basename(path))
    	
    def check(self):
        """Check the remote build host to see if the relevant software to build packages is installed"""
        with settings(warn_only=True):
            # check for fpm
            result = run('which fpm')
            if result.return_code:
                raise Exception("Build host does not have fpm installed and on the executable path")
            
            # check for checkinstall
            result = run('which checkinstall')
            if result.return_code:
                raise Exception("Build host does not have checkinstall installed and on the executable path")
        
    def setup(self):
        """this method sets up a remote debian box for parcel package building.
        Installs fpm, easyinstall and some libraries

        there must be a a directory called archives
        and in it a file rubygems-1.8.24.tgz

        TODO: remove this requirement. get the file we need.
        """
        with settings(user='root'):
            self.build_deps(['libyaml-ruby','libzlib-ruby','ruby','ruby-dev','checkinstall'])

            base_dir, src_dir, build_dir = self._setup()
            self.push_files(["archives/rubygems-1.8.24.tgz"],src_dir)                   # todo: get rubygems if its not present.
            with cd(build_dir):
                run("tar xvfz ../src/rubygems-1.8.24.tgz")
            with cd(build_dir+"/rubygems-1.8.24"):
                run("ruby setup.rb")
            run("gem1.8 install fpm")



    