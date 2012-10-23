import os.path

from fabric.api import settings, run, cd, lcd, put, get, local, env, with_settings

from . import versions
from . import distro
from . import tools

class Deployment(object):
    virtual = "vp"
    build_dir = '.parcel'
    
    def __init__(self, app_name, build_deps=[], run_deps=[], path=".", base=None,arch=distro.Debian()):
        """app_name: the package name
        build_deps: a list of packages that need to be installed to build the software
        run_deps: a list of packages that must be installed to run
        path: the directory to end up being the base level directory.
        base: where the path will be located on the build host. default is use homedir.
                if path is relative, its relative to remote homedir
                if path is absolute, its the path.
        arch: the architecture of the build host
        """
        self.arch = arch
        remotehome = run('echo $HOME').strip()
        
        # if path isn't set, make it the home directory of the build user
        if base is None:
            base = remotehome
        elif not base.startswith('/'):
            base = os.path.join(remotehome, base)
        
        # update and install missing build dependency packages
        arch.update_packages()
        if build_deps:
            arch.build_deps(build_deps)
            
        # the version in the archives of this package if we have been built and uploaded before.
        self.version = arch.version(app_name)
        
        self.app_name = app_name
        self.run_deps = run_deps
        self.build_deps = build_deps
        self.pkg_name = app_name.lower()

        self.path = os.path.realpath(path)

	    # the path we build everything on on the remote host
        self.base_path = os.path.join(remotehome,self.build_dir)
        self.root_path = os.path.join(self.base_path,"root")                    # where the final root fs is located
        
        # the path the app will be installed into
        self.app_path = os.path.join(base,'%s-%s'%(self.pkg_name,self.version))
        
        # the build path
        self.build_path = os.path.join(self.root_path, self.app_path[1:])                # cut the first / off app_path
            
        print "BASE_PATH",self.base_path
        print "APP PATH",self.app_path
        print "BUILD PATH",self.build_path
        
        self.clean()
        
    def clean(self):
        # make sure this root fs directory is empty
        run('rm -rf "%s"'%self.root_path)
        
    def prepare_app(self, branch=None, requirements="requirements.txt"):
        """creates the necessary directories on the build server, checks out the desired branch (None means current),
        creates a virtualenv and populates it with dependencies from requirements.txt. 
        As a bonus it also fixes the shebangs ("#!") of all scripts in the virtualenv to point the correct Python path on the target system."""
        
        # theres no revision control atm so... just copy directory over
        tools.rsync([self.path+'/'],self.build_path,rsync_ignore='.rsync-ignore')
        
        self.venv_path = os.path.join(self.build_path, self.virtual)
        run('virtualenv %s'%(self.venv_path))
        if requirements:
            run('PIP_DOWNLOAD_CACHE="%s" %s install -r %s'%(
                self.arch.pip_download_cache,
	            os.path.join(self.venv_path, 'bin/pip'),
	            os.path.join(self.build_path, requirements))
            )
            
        # venv_root is final path
        self.venv_root = os.path.join(self.app_path, self.virtual)
        
    def add_to_root_fs(self,localfile,remotepath):
        """add a local file to the root package path.
        if remote path ends in /, the filename is carried over and into
        that directory. If the remote path doesnt end in /, it represents the final filename
        """
        while remotepath[0]=='/':
            remotepath=remotepath[1:]
        put(localfile,os.path.join(self.root_path,remotepath))
        
    def add_data_to_root_fs(self, data, remotepath):
        """sticks data in file on remotepath (relative to final root"""
        while remotepath[0]=='/':
            remotepath=remotepath[1:]
        tools.write_contents_to_remote(data,os.path.join(self.root_path, remotepath))
            
    def compile_python(self):
        # compile all python (with virtual python)
        run('%s -c "import compileall;compileall.compile_dir(\'%s\', force=1)"'%(os.path.join(self.venv_path, 'bin/python'),self.app_path))

    def clear_py_files():
        # clear all .py files
        run('find "%s" -name "*.py" -exec rm {} \;'%(self.app_path))

    def build_deb(self):
        """takes the whole app including the virtualenv, packages it using fpm and downloads it to my local host.
	    The version of the package is the build number - which is just the latest package version in our Ubuntu repositories plus one.
	    """
        with cd(self.base_path):
            self.run_deps.append('python-virtualenv')                   
            deps_str = '-d ' + ' -d '.join(self.run_deps)
            dirs_str = self.app_path

            hooks_str = ''
            rv = run(
                'fpm -s dir -t deb -n {0.pkg_name} -v {0.version} '
                '-a all -x "*.git" -x "*.bak" -x "*.orig" {1} '
                '--description "Automated build. '
                'No Version Control." '
                '{2} {3}'
                .format(self, hooks_str, deps_str, dirs_str)
            )

            filename = rv.split('"')[-2]
            get(filename, './')
            run("rm '%s'"%filename)

# try supervisord functionality as a mixin?
class supervisord(object):
    def add_supervisord_service(self):
        self.add_data_to_root_fs("""[program:uwsgi]
command=/usr/local/bin/uwsgi --ini=/etc/uwsgi/app.uswgi
process_name=%(program_name)s
numprocs=1
directory=/tmp
umask=022
priority=999
autostart=true
autorestart=true
startsecs=10
startretries=3
exitcodes=0,2
stopsignal=TERM
stopwaitsecs=10
user=crispin
redirect_stderr=false
stdout_logfile=/var/log/uwsgi.log
stdout_logfile_maxbytes=1MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
serverurl=AUTO
""","etc/supervisor/conf.d/uwsgi.conf")
        


class uWSGI(Deployment, supervisord):
    PRERM="""#!/bin/sh

#set -e

APP_NAME={0.app_name}

case "$1" in
    upgrade|failed-upgrade|abort-install|abort-upgrade|disappear|purge|remove)
        supervisorctl stop uwsgi
    ;;

    *)
        echo "prerm called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac
"""

    POSTRM=None
    PREINST=None
    POSTINST="""#!/bin/sh

#set -e

APP_NAME={0.app_name}

case "$1" in
    configure)
        virtualenv {0.venv_root}
        /etc/init.d/supervisor stop
        sleep 1
        /etc/init.d/supervisor start
        #supervisorctl start uwsgi
    ;;

    abort-upgrade|abort-remove|abort-deconfigure)
    ;;

    *)
        echo "postinst called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac
"""

    def build_deb(self):
        self.write_uwsgi_file(port=8000, path=self.app_path, module='%s.wsgi'%(self.app_name))
        self.add_supervisord_service()
    
        with cd(self.base_path):
            self.run_deps.append('python-virtualenv')  
            self.run_deps.append('supervisor')                 
            deps_str = '-d ' + ' -d '.join(self.run_deps)
            dirs_str = '.'
            
            run("rm -rf debian && mkdir -p debian")
            
            # render pre/posts
            hooks = []
            if self.PRERM:
                prerm = self.PRERM.format(self)
                tools.write_contents_to_remote(prerm,'debian/prerm')
                hooks.extend(['--before-remove', '../debian/prerm'])
                
            if self.POSTRM:
                postrm = self.POSTRM.format(self)
                tools.write_contents_to_remote(postrm,'debian/postrm')
                hooks.extend(['--after-remove', '../debian/postrm'])
            
            if self.PREINST:
                preinst = self.PREINST.format(self)
                tools.write_contents_to_remote(preinst,'debian/preinst')
                hooks.extend(['--before-install', '../debian/preinst'])
            
            if self.POSTINST:
                postinst = self.POSTINST.format(self)
                tools.write_contents_to_remote(postinst,'debian/postinst')
                hooks.extend(['--after-install', '../debian/postinst'])
            
            hooks_str = ' '.join(hooks)
            
        with cd(self.root_path):
            rv = run(
                'fpm -s dir -t deb -n {0.pkg_name} -v {0.version} '
                '-a all -x "*.git" -x "*.bak" -x "*.orig" {1} '
                '--description "Automated build. '
                'No Version Control." '
                '{2} {3}'
                .format(self, hooks_str, deps_str, dirs_str)
            )

            filename = rv.split('"')[-2]
            get(filename, './')
            run("rm '%s'"%filename)
        
    def write_uwsgi_file(self,port,path,module):
        data = """[uwsgi]
# set the http port
http = :%d
# change to django project directory
chdir = %s/%s
# load django
module = %s
home = %s
"""%(port,path,self.app_name,module,self.venv_root)
        self.add_data_to_root_fs(data,'/etc/uwsgi/app.uswgi')
        
        
