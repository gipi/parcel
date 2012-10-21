# helper utils
from fabric.api import env, local, run, put, get
import requests
import os, tempfile, uuid

BLOCK_SIZE = 8192

def dl(url,filename):
    """download a url from the net and saves it as filename.
    
    Data is streamed so large files can be saved without exhausting memory
    """
    r=requests.get(url)
    assert r.status_code==200
    
    with open(filename,'wb') as fh:
        for data in r.iter_content(BLOCK_SIZE):
            fh.write(data)

def rsync(sources,dest,rsync_ignore=None):
    assert type(sources)!=str, "Must pass a list of sources into rsync"
    run('mkdir -p "%s"'%dest)
    
    command =   [   'rsync',
                    '-av',
                ] + [
                 "'%s'"%s for s in sources
                ] + [
                    "'%s@%s:%s'"%(env.user,env.host,dest)
                ]
                
    if rsync_ignore:
        if os.path.isfile(rsync_ignore):
            command.append('--exclude-from=%s'%rsync_ignore)
    
    
                
    local(" ".join(command))
    
def write_contents_to_remote(data,filename):
    """creates a file on remote 'filename' that has contents 'data'
    """
    # write a teporary file
    fd,name = tempfile.mkstemp()
    with open(name,'w') as fh:
        fh.write(data)
        
    # copy it
    try:
        put(name,filename)
    finally:
        os.unlink(name)
    
def read_contents_from_remote(remote):
    """returns the data in the remote file. WARNING: reads into ram. only small control files"""
    # copy back to temporary file
    fd,name = tempfile.mkstemp()
    os.unlink(name)
    get(remote,name)
    
    with open(name,'r') as fh:
        data = fh.read()
        
    os.unlink(name)
    return data

def quiet_run(command):
    """Issues a run with the command but pipes the output to a temp file
    then reads the tempfile back here to be presented as data
    """
    remote_temp = "/tmp/%s.tmp"%uuid.uuid4()
    
    run(command+" 1> '%s'"%remote_temp)
    
    data = read_contents_from_remote(remote_temp)
    
    run('rm -f "%s"'%remote_temp)
    
    return data
    
    
    
