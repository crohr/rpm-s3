#!/usr/bin/python
# util functions for createrepo
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.



import os
import os.path
import sys
import bz2
import gzip
from gzip import write32u, FNAME
from yum import misc
_available_compression = ['gz', 'bz2']
try:
    import lzma
    _available_compression.append('xz')
except ImportError:
    lzma = None

def errorprint(stuff):
    print >> sys.stderr, stuff

def _(args):
    """Stub function for translation"""
    return args


class GzipFile(gzip.GzipFile):
    def _write_gzip_header(self):
        # Generate a header that is easily reproduced with gzip -9 -n on
        # an unix-like system
        self.fileobj.write('\037\213')             # magic header
        self.fileobj.write('\010')                 # compression method
        self.fileobj.write('\000')                 # flags
        write32u(self.fileobj, long(0))            # timestamp
        self.fileobj.write('\002')                 # max compression
        self.fileobj.write('\003')                 # UNIX

def _gzipOpen(filename, mode="rb", compresslevel=9):
    return GzipFile(filename, mode, compresslevel)

def bzipFile(source, dest):

    s_fn = open(source, 'rb')
    destination = bz2.BZ2File(dest, 'w', compresslevel=9)

    while True:
        data = s_fn.read(1024000)

        if not data: break
        destination.write(data)

    destination.close()
    s_fn.close()


def xzFile(source, dest):
    if not 'xz' in _available_compression:
        raise MDError, "Cannot use xz for compression, library/module is not available"
        
    s_fn = open(source, 'rb')
    destination = lzma.LZMAFile(dest, 'w')

    while True:
        data = s_fn.read(1024000)

        if not data: break
        destination.write(data)

    destination.close()
    s_fn.close()

def gzFile(source, dest):
        
    s_fn = open(source, 'rb')
    destination = GzipFile(dest, 'w')

    while True:
        data = s_fn.read(1024000)

        if not data: break
        destination.write(data)

    destination.close()
    s_fn.close()


class Duck:
    def __init__(self, **attr):
        self.__dict__ = attr


def compressFile(source, dest, compress_type):
    """Compress an existing file using any compression type from source to dest"""
    
    if compress_type == 'xz':
        xzFile(source, dest)
    elif compress_type == 'bz2':
        bzipFile(source, dest)
    elif compress_type == 'gz':
        gzFile(source, dest)
    else:
        raise MDError, "Unknown compression type %s" % compress_type
    
def compressOpen(fn, mode='rb', compress_type=None):
    
    if not compress_type:
        # we are readonly and we don't give a compress_type - then guess based on the file extension
        compress_type = fn.split('.')[-1]
        if compress_type not in _available_compression:
            compress_type = 'gz'
            
    if compress_type == 'xz':
        fh = lzma.LZMAFile(fn, mode)
        if mode == 'w':
            fh = Duck(write=lambda s, write=fh.write: s != '' and write(s),
                      close=fh.close)
        return fh
    elif compress_type == 'bz2':
        return bz2.BZ2File(fn, mode)
    elif compress_type == 'gz':
        return _gzipOpen(fn, mode)
    else:
        raise MDError, "Unknown compression type %s" % compress_type
    
def returnFD(filename):
    try:
        fdno = os.open(filename, os.O_RDONLY)
    except OSError:
        raise MDError, "Error opening file"
    return fdno

def checkAndMakeDir(directory):
    """
     check out the directory and make it, if possible, return 1 if done, else return 0
    """
    if os.path.exists(directory):
        if not os.path.isdir(directory):
            #errorprint(_('%s is not a dir') % directory)
            result = False
        else:
            if not os.access(directory, os.W_OK):
                #errorprint(_('%s is not writable') % directory)
                result = False
            else:
                result = True
    else:
        try:
            os.mkdir(directory)
        except OSError, e:
            #errorprint(_('Error creating dir %s: %s') % (directory, e))
            result = False
        else:
            result = True
    return result

def checksum_and_rename(fn_path, sumtype='sha256'):
    """checksum the file rename the file to contain the checksum as a prefix
       return the new filename"""
    csum = misc.checksum(sumtype, fn_path)
    fn = os.path.basename(fn_path)
    fndir = os.path.dirname(fn_path)
    csum_fn = csum + '-' + fn
    csum_path = os.path.join(fndir, csum_fn)
    os.rename(fn_path, csum_path)
    return (csum, csum_path)



def encodefilenamelist(filenamelist):
    return '/'.join(filenamelist)

def encodefiletypelist(filetypelist):
    result = ''
    ftl = {'file':'f', 'dir':'d', 'ghost':'g'}
    for x in filetypelist:
        result += ftl[x]
    return result

def split_list_into_equal_chunks(seq, num_chunks):
    """it's used on sorted input which is then merged in order"""
    out = [[] for i in range(num_chunks)]
    for i, item in enumerate(seq):
        out[i % num_chunks].append(item)
    return out

def num_cpus_online(unknown=1):
    if not hasattr(os, "sysconf"):
        return unknown

    if not os.sysconf_names.has_key("SC_NPROCESSORS_ONLN"):
        return unknown

    ncpus = os.sysconf("SC_NPROCESSORS_ONLN")
    try:
        if int(ncpus) > 0:
            return ncpus
    except:
        pass

    return unknown


class MDError(Exception):
    def __init__(self, value=None):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return self.value
