#!/usr/bin/python -t

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
# Copyright 2006 Red Hat

import os
import stat
from utils import errorprint, _

import yum
from yum import misc
from yum.Errors import YumBaseError
import tempfile
class CreaterepoPkgOld(yum.sqlitesack.YumAvailablePackageSqlite):
    # special for special people like us.
    def _return_remote_location(self):

        if self.basepath:
            msg = """<location xml:base="%s" href="%s"/>\n""" % (
                                     misc.to_xml(self.basepath, attrib=True),
                                     misc.to_xml(self.relativepath, attrib=True))
        else:
            msg = """<location href="%s"/>\n""" % misc.to_xml(self.relativepath, attrib=True)

        return msg  


class MetadataIndex(object):

    def __init__(self, outputdir, opts=None):
        if opts is None:
            opts = {}
        self.opts = opts
        self.outputdir = outputdir
        realpath = os.path.realpath(outputdir)
        repodatadir = self.outputdir + '/repodata'
        self._repo = yum.yumRepo.YumRepository('garbageid')
        self._repo.baseurl = 'file://' + realpath
        self._repo.basecachedir = tempfile.mkdtemp(dir='/var/tmp', prefix="createrepo")
        self._repo.base_persistdir = tempfile.mkdtemp(dir='/var/tmp', prefix="createrepo-p")
        self._repo.metadata_expire = 1
        self._repo.gpgcheck = 0
        self._repo.repo_gpgcheck = 0
        self._repo._sack = yum.sqlitesack.YumSqlitePackageSack(CreaterepoPkgOld)
        self.pkg_tups_by_path = {}
        try:
            self.scan()
        except YumBaseError, e:
            print "Could not find valid repo at: %s" % self.outputdir
        

    def scan(self):
        """Read in old repodata"""
        if self.opts.get('verbose'):
            print _("Scanning old repo data")
        self._repo.sack.populate(self._repo, 'all', None, False)
        for thispo in self._repo.sack:
            mtime = thispo.filetime
            size = thispo.size
            relpath = thispo.relativepath
            do_stat = self.opts.get('do_stat', True)
            if mtime is None:
                print _("mtime missing for %s") % relpath
                continue
            if size is None:
                print _("size missing for %s") % relpath
                continue
            if do_stat:
                filepath = os.path.join(self.opts['pkgdir'], relpath)
                try:
                    st = os.stat(filepath)
                except OSError:
                    #file missing -- ignore
                    continue
                if not stat.S_ISREG(st.st_mode):
                    #ignore non files
                    continue
                #check size and mtime
                if st.st_size != size:
                    if self.opts.get('verbose'):
                        print _("Size (%i -> %i) changed for file %s") % (size,st.st_size,filepath)
                    continue
                if int(st.st_mtime) != mtime:
                    if self.opts.get('verbose'):
                        print _("Modification time changed for %s") % filepath
                    continue

            self.pkg_tups_by_path[relpath] = thispo.pkgtup



    def getNodes(self, relpath):
        """return a package object based on relative path of pkg
        """
        if relpath in self.pkg_tups_by_path:
            pkgtup = self.pkg_tups_by_path[relpath]
            return self._repo.sack.searchPkgTuple(pkgtup)[0]
        return None

    

if __name__ == "__main__":
    cwd = os.getcwd()
    opts = {'verbose':1,
            'pkgdir': cwd}

    idx = MetadataIndex(cwd, opts)
    for fn in idx.pkg_tups_by_path:
        po = idx.getNodes(fn)
        print po.xml_dump_primary_metadata()
        print po.xml_dump_filelists_metadata()
        print po.xml_dump_other_metadata()

