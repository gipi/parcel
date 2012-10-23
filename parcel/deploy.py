import os.path

from fabric.api import settings, run, cd, lcd, put, get, local, env, with_settings, task
from fabric.tasks import Task

from . import versions
from . import distro
from . import tools

env.app_name = 'default_app_name'
env.run_deps = []
env.build_deps = []
env.base = None
env.path = '.'
env.arch = distro.Debian()

class Deployment(object):
    virtual = "vp"
    build_dir = '.parcel'
    
    # these are the full text versions of the scripts
    prerm = None
    postrm = None
    preinst = None
    postinst = None
    
    # these are a list representation of commands to go into the scripts
    # if the control script templating is used
    prerm_lines = []
    postrm_lines = []
    preinst_lines = []
    postinst_lines = []
    
    def __init__(self, app_name=env.app_name, build_deps=env.build_deps,
                 run_deps=env.run_deps, path=env.path, base=env.base,arch=env.arch):
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
        
    def sync_app(self):
        # theres no revision control atm so... just copy directory over
        tools.rsync([self.path+'/'],self.build_path,rsync_ignore='.rsync-ignore')
        
    def prepare_app(self, branch=None, requirements="requirements.txt"):
        """creates the necessary directories on the build server, checks out the desired branch (None means current),
        creates a virtualenv and populates it with dependencies from requirements.txt. 
        As a bonus it also fixes the shebangs ("#!") of all scripts in the virtualenv to point the correct Python path on the target system."""
        self.sync_app()
        self.add_venv(requirements)
    
    def add_venv(self,requirements="requirements.txt"):
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
        
        # lets make sure this venv is relinked on installation
        self.add_postinst(['virtualenv "%s"'%self.venv_root])
        
        # and we have the virtualenv executable
        self.run_deps.append('python-virtualenv')  
            
        
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

    def clear_py_files(self):
        # clear all .py files
        run('find "%s" -name "*.py" -exec rm {} \;'%(self.app_path))

    def add_prerm(self, lines):
        self.prerm_lines.extend(lines)
        
    def add_postrm(self, lines):
        self.postrm_lines.extend(lines)
        
    def add_preinst(self, lines):
        self.preinst_lines.extend(lines)
        
    def add_postinst(self, lines):
        self.postinst_lines.extend(lines)
        
    def build_deb(self, templates=True):
        """takes the whole app including the virtualenv, packages it using fpm and downloads it to my local host.
	    The version of the package is the build number - which is just the latest package version in our Ubuntu repositories plus one.
	    """
        if templates:
            self.write_prerm_template()
            self.write_postinst_template()
        
        with cd(self.base_path):
            deps_str = '-d ' + ' -d '.join(self.run_deps)
            dirs_str = '.'
            
            if self.prerm or self.postrm or self.preinst or self.postinst:
                run("rm -rf debian && mkdir -p debian")
            
            # render pre/posts
            hooks = []
            if self.prerm:
                prerm = self.prerm.format(self)
                tools.write_contents_to_remote(prerm,'debian/prerm')
                hooks.extend(['--before-remove', '../debian/prerm'])
                
            if self.postrm:
                postrm = self.postrm.format(self)
                tools.write_contents_to_remote(postrm,'debian/postrm')
                hooks.extend(['--after-remove', '../debian/postrm'])
            
            if self.preinst:
                preinst = self.preinst.format(self)
                tools.write_contents_to_remote(preinst,'debian/preinst')
                hooks.extend(['--before-install', '../debian/preinst'])
            
            if self.postinst:
                postinst = self.postinst.format(self)
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

    def write_prerm_template(self):
        prerm_template = """#!/bin/sh

set -e

APP_NAME={0.app_name}

case "$1" in
    upgrade|failed-upgrade|abort-install|abort-upgrade|disappear|purge|remove)
        %s
    ;;

    *)
        echo "prerm called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac
"""
        self.prerm = prerm_template%("\n        ".join(self.prerm_lines))     

    def write_postinst_template(self):
        postinst_template="""#!/bin/sh

set -e

APP_NAME={0.app_name}

case "$1" in
    configure)
        %s
    ;;

    abort-upgrade|abort-remove|abort-deconfigure)
    ;;

    *)
        echo "postinst called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac
"""
        self.postinst = postinst_template%("\n        ".join(self.postinst_lines))




##
## supervisord + uwsgi container deployment
##
class uWSGI(Deployment):
    def add_supervisord_uwsgi_service(self,program_name,port=80,user=None):
        # add the config file
        self.add_data_to_root_fs("""[program:%s]
command=/usr/local/bin/uwsgi --ini=/etc/uwsgi/%s.uswgi
process_name=%s
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
user=%s
redirect_stderr=false
stdout_logfile=/var/log/%s.log
stdout_logfile_maxbytes=1MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
serverurl=AUTO
"""%(program_name, program_name, program_name, user or env.user, program_name), "etc/supervisor/conf.d/uwsgi.conf")
        
        # add the postinstall lines
        self.add_postinst(['/etc/init.d/supervisor stop','sleep 1','/etc/init.d/supervisor start'])
        
        # add the prerm lines
        self.add_prerm(['supervisorctl stop %s'%program_name])
        
        # add the supervisor install dependency
        self.run_deps.append('supervisor')              # also uwsgi on systems with it in packaging (redhat? ubuntu?)

        # write out our uwsgi config
        self.write_uwsgi_file(port=port, path=self.app_path, module='%s.wsgi'%(self.app_name), program_name=program_name)
        
        # also in postinst is to start this app
        self.add_postinst(['supervisorctl start %s'%program_name])
        
    def write_uwsgi_file(self,port,path,module,program_name):
        data = """[uwsgi]
# set the http port
http = :%d
# change to django project directory
chdir = %s/%s
# load django
module = %s
home = %s
"""%(port,path,self.app_name,module,self.venv_root)
        self.add_data_to_root_fs(data,'/etc/uwsgi/%s.uswgi'%program_name)
        

@task
def build():
    deploy = Deployment(app_name=env.app_name, build_deps=env.build_deps,
                    run_deps=env.run_deps, path=env.path, base=env.base,arch=env.arch)
    deploy.clean()
    deploy.prepare_app()
    deploy.build_deb()

@task
def build_for_uwsgi():
    assert env.service_name, "You need to set env.service_name"
    assert env.port, "You need to set env.port"
    deploy = uWSGI(app_name=env.app_name, build_deps=env.build_deps,
                    run_deps=env.run_deps, path=env.path, base=env.base,arch=env.arch)
    deploy.clean()
    deploy.prepare_app()
    deploy.add_supervisord_uwsgi_service(env.service_name, env.port)
    deploy.build_deb()
