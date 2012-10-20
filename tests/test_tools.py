import unittest2 as unittest
from fabric.api import run
import tempfile

from mixins import WebServerMixin
from parcel.tools import dl, rpull, rpush

def tempname():
    return tempfile.mkstemp()[1]
    
import zlib, os

def crc32(filename):
    CHUNKSIZE = 8192
    checksum = 0
    with open(filename, 'rb') as fh:
        bytes = fh.read(CHUNKSIZE)
        while bytes:
            checksum = zlib.crc32(bytes, checksum)
            bytes = fh.read(CHUNKSIZE)
    return checksum


class ToolsTestSuite(unittest.TestCase, WebServerMixin):
    """Tools test cases."""
    
    def test_dl(self):
        self.startWebServer()
        
        filename = tempname()
        
        dl("http://localhost:%s/tip.tar.gz"%self.port,filename)
        
        # there should be no differences between the files
        self.assertEquals(crc32(filename),crc32(os.path.join(self.webroot,'tip.tar.gz')))
        
        # shutdown webserver
        self.stopWebServer()
        
