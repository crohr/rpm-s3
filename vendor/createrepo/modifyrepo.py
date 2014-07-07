#!/usr/bin/python
# This tool is used to manipulate arbitrary metadata in a RPM repository.
# Example:
#           ./modifyrepo.py updateinfo.xml myrepo/repodata
#           or
#           ./modifyrepo.py --remove updateinfo.xml myrepo/repodata
# or in Python:
#           >>> from modifyrepo import RepoMetadata
#           >>> repomd = RepoMetadata('myrepo/repodata')
#           >>> repomd.add('updateinfo.xml')
#           or
#           >>> repomd.remove('updateinfo.xml')
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# (C) Copyright 2006  Red Hat, Inc.
# Luke Macken <lmacken@redhat.com>
# modified by Seth Vidal 2008
# modified by Daniel Mach 2011

import os
import re
import sys
from createrepo import __version__
from createrepo.utils import checksum_and_rename, compressOpen, MDError
from createrepo.utils import _available_compression
from yum.misc import checksum, _available_checksums, AutoFileChecksums

from yum.repoMDObject import RepoMD, RepoMDError, RepoData
from xml.dom import minidom
from optparse import OptionParser


class RepoMetadata:

    def __init__(self, repo):
        """ Parses the repomd.xml file existing in the given repo directory. """
        self.repodir = os.path.abspath(repo)
        self.repomdxml = os.path.join(self.repodir, 'repomd.xml')
        self.compress_type = _available_compression[-1] # best available

        if not os.path.exists(self.repomdxml):
            raise MDError, '%s not found' % self.repomdxml

        try:
            self.repoobj = RepoMD(self.repodir)
            self.repoobj.parse(self.repomdxml)
        except RepoMDError, e:
            raise MDError, 'Could not parse %s' % self.repomdxml

    def _get_mdtype(self, mdname, mdtype=None):
        """ Get mdtype from existing mdtype or from a mdname. """
        if mdtype:
            return mdtype
        mdname = os.path.basename(mdname)
        if re.match(r'[0-9a-f]{32,}-', mdname):
            mdname = mdname.split('-', 1)[1]
        return mdname.split('.')[0]

    def _print_repodata(self, repodata):
        """ Print repodata details. """
        print "           type =", repodata.type
        print "       location =", repodata.location[1]
        print "       checksum =", repodata.checksum[1]
        print "      timestamp =", repodata.timestamp
        print "  open-checksum =", repodata.openchecksum[1]
        print "           size =", repodata.size
        print "      open-size =", repodata.opensize

    def _write_repomd(self):
        """ Write the updated repomd.xml. """
        outmd = file(self.repomdxml, 'w')
        outmd.write(self.repoobj.dump_xml())
        outmd.close()
        print "Wrote:", self.repomdxml

    def _remove_repodata_file(self, repodata):
        """ Remove a file specified in repodata location """
        try:
            fname = os.path.basename(repodata.location[1])
            os.remove(os.path.join(self.repodir, fname))
        except OSError, ex:
            if ex.errno != 2:
                # continue on a missing file
                raise MDError("could not remove file %s" % repodata.location[1])

    def add(self, metadata, mdtype=None):
        """ Insert arbitrary metadata into this repository.
            metadata can be either an xml.dom.minidom.Document object, or
            a filename.
        """
        md = None
        if not metadata:
            raise MDError, 'metadata cannot be None'
        if isinstance(metadata, minidom.Document):
            md = metadata.toxml()
            mdname = 'updateinfo.xml'
        elif isinstance(metadata, str):
            if os.path.exists(metadata):
                mdname = os.path.basename(metadata)
                if mdname.split('.')[-1] in ('gz', 'bz2', 'xz'):
                    mdname = mdname.rsplit('.', 1)[0]
                    oldmd = compressOpen(metadata, mode='rb')
                else:
                    oldmd = file(metadata, 'r')
                oldmd = AutoFileChecksums(oldmd, [self.checksum_type])
                md = oldmd.read()
                oldmd.close()
            else:
                raise MDError, '%s not found' % metadata
        else:
            raise MDError, 'invalid metadata type'

        ## Compress the metadata and move it into the repodata
        mdtype = self._get_mdtype(mdname, mdtype)
        destmd = os.path.join(self.repodir, mdname)
        if self.compress:
            destmd += '.' + self.compress_type
            newmd = compressOpen(destmd, mode='wb', compress_type=self.compress_type)
        else:
            newmd = open(destmd, 'wb')
            
        newmd.write(md)
        newmd.close()
        print "Wrote:", destmd

        if self.unique_md_filenames:
            csum, destmd = checksum_and_rename(destmd, self.checksum_type)
        else:
            csum = checksum(self.checksum_type, destmd)
        base_destmd = os.path.basename(destmd)

        # Remove any stale metadata
        old_rd = self.repoobj.repoData.pop(mdtype, None)

        new_rd = RepoData()
        new_rd.type = mdtype
        new_rd.location = (None, 'repodata/' + base_destmd)
        new_rd.checksum = (self.checksum_type, csum)
        new_rd.size = str(os.stat(destmd).st_size)
        if self.compress:
            new_rd.openchecksum = oldmd.checksums.hexdigests().popitem()
            new_rd.opensize = str(oldmd.checksums.length)
        new_rd.timestamp = str(int(os.stat(destmd).st_mtime))
        self.repoobj.repoData[new_rd.type] = new_rd
        self._print_repodata(new_rd)
        self._write_repomd()

        if old_rd is not None and old_rd.location[1] != new_rd.location[1]:
            # remove the old file when overwriting metadata
            # with the same mdtype but different location
            self._remove_repodata_file(old_rd)

    def remove(self, metadata, mdtype=None):
        """ Remove metadata from this repository. """
        mdname = metadata
        mdtype = self._get_mdtype(mdname, mdtype)

        old_rd = self.repoobj.repoData.pop(mdtype, None)
        if old_rd is None:
            print "Metadata not found: %s" % mdtype
            return

        self._remove_repodata_file(old_rd)
        print "Removed:"
        self._print_repodata(old_rd)
        self._write_repomd()


def main(args):
    parser = OptionParser(version='modifyrepo version %s' % __version__)
    # query options
    parser.add_option("--mdtype", dest='mdtype',
                      help="specific datatype of the metadata, will be derived from the filename if not specified")
    parser.add_option("--remove", action="store_true",
                      help="remove specified file from repodata")
    parser.add_option("--compress", action="store_true", default=True,
                      help="compress the new repodata before adding it to the repo (default)")
    parser.add_option("--no-compress", action="store_false", dest="compress",
                      help="do not compress the new repodata before adding it to the repo")
    parser.add_option("--compress-type", dest='compress_type',
                      help="compression format to use")
    parser.add_option("-s", "--checksum", dest='sumtype',
        help="specify the checksum type to use")
    parser.add_option("--unique-md-filenames", dest="unique_md_filenames",
        help="include the file's checksum in the filename, helps with proxies",
        action="store_true")
    parser.add_option("--simple-md-filenames", dest="unique_md_filenames",
        help="do not include the file's checksum in the filename",
        action="store_false")
    parser.usage = "modifyrepo [options] [--remove] <input_metadata> <output repodata>"
    
    (opts, argsleft) = parser.parse_args(args)
    if len(argsleft) != 2:
        parser.print_usage()
        return 0
    metadata = argsleft[0]
    repodir = argsleft[1]
    try:
        repomd = RepoMetadata(repodir)
    except MDError, e:
        print "Could not access repository: %s" % str(e)
        return 1

    try:
        # try to extract defaults from primary entry
        md = repomd.repoobj.getData('primary')
        sumtype = md.checksum[0]
        name = os.path.basename(md.location[1])
        unique_md_filenames = re.match(r'[0-9a-f]{32,}-', name) != None
        compress_type = name.rsplit('.', 1)[1]
    except RepoMDError:
        sumtype = 'sha256'
        unique_md_filenames = True
        compress_type = 'gz'

    # apply defaults
    if opts.sumtype is None:
        opts.sumtype = sumtype
    if opts.unique_md_filenames is None:
        opts.unique_md_filenames = unique_md_filenames
    if opts.compress_type is None:
        opts.compress_type = compress_type

    repomd.checksum_type = opts.sumtype
    repomd.unique_md_filenames = opts.unique_md_filenames
    repomd.compress = opts.compress
    if opts.compress_type not in _available_compression:
        print "Compression %s not available: Please choose from: %s" % (opts.compress_type, ', '.join(_available_compression))
        return 1
    if opts.sumtype not in _available_checksums:
        print "Checksum %s not available: Please choose from: %s" % (opts.sumtype, ', '.join(_available_checksums))
        return 1
    repomd.compress_type = opts.compress_type

    # remove
    if opts.remove:
        try:
            repomd.remove(metadata, mdtype=opts.mdtype)
        except MDError, ex:
            print "Could not remove metadata: %s" % (metadata, str(ex))
            return 1
        return

    # add
    try:
        repomd.add(metadata, mdtype=opts.mdtype)
    except MDError, e:
        print "Could not add metadata from file %s: %s" % (metadata, str(e))
        return 1
    

if __name__ == '__main__':
    ret = main(sys.argv[1:])
    sys.exit(ret)
