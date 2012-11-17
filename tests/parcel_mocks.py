import os
import mock
from functools import partial

from fabric.colors import blue
from fabric.api import local

from parcel.versions import Version


# fabric.api
run = mock.MagicMock(name='run')
local = partial(local, capture=True)

# fabric.colors
green = mock.MagicMock(name='green')
blue = mock.MagicMock(name='blue')

# fabric.contrib.files
append = mock.MagicMock(name="append")

# rsync
rsync = mock.MagicMock(name='rsync')

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

    print "DEST>>>>>>>>>>>>>>>>>" + dest

    local('mkdir -p "%s"'%dest)
    data = ''

    print sources
    print dest

    for s in sources:
        data += local('cp -R {0} {1}/'.format(s, dest))

    print data


    ## lines = data.splitlines()
    ## lines = lines[1:]
    ## i=0
    ## while lines[i]:
    ##     print blue(lines[i])
    ##     i+=1
    ## for line in lines[i:]:
    ##     print line     

    return

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
