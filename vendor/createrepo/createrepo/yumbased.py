#!/usr/bin/python -tt
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
# Copyright 2007  Red Hat, Inc - written by seth vidal skvidal at fedoraproject.org


import os
def _get_umask():
   oumask = os.umask(0)
   os.umask(oumask)
   return oumask
_b4rpm_oumask = _get_umask()
import rpm
import types

from yum.packages import YumLocalPackage
from yum.Errors import *
from yum import misc
import utils
import tempfile

class CreateRepoPackage(YumLocalPackage):
    def __init__(self, ts, package, sumtype=None, external_data={}):
        YumLocalPackage.__init__(self, ts, package)
        if sumtype:
            self.checksum_type = sumtype
        
        if external_data:
            for (key, val) in external_data.items():
                setattr(self, key, val)
                

    def _do_checksum(self):
        """return a checksum for a package:
           - check if the checksum cache is enabled
              if not - return the checksum
              if so - check to see if it has a cache file
                if so, open it and return the first line's contents
                if not, grab the checksum and write it to a file for this pkg
         """
        # already got it
        if self._checksum:
            return self._checksum

        # not using the cachedir
        if not hasattr(self, '_cachedir') or not self._cachedir:
            self._checksum = misc.checksum(self.checksum_type, self.localpath)
            self._checksums = [(self.checksum_type, self._checksum, 1)]
            return self._checksum


        t = []
        if type(self.hdr[rpm.RPMTAG_SIGGPG]) is not types.NoneType:
            t.append("".join(self.hdr[rpm.RPMTAG_SIGGPG]))
        if type(self.hdr[rpm.RPMTAG_SIGPGP]) is not types.NoneType:
            t.append("".join(self.hdr[rpm.RPMTAG_SIGPGP]))
        if type(self.hdr[rpm.RPMTAG_HDRID]) is not types.NoneType:
            t.append("".join(self.hdr[rpm.RPMTAG_HDRID]))

        kcsum = misc.Checksums(checksums=[self.checksum_type])
        kcsum.update("".join(t))
        key = kcsum.hexdigest()

        csumtag = '%s-%s-%s-%s' % (os.path.basename(self.localpath),
                                   key, self.size, self.filetime)
        csumfile = '%s/%s' % (self._cachedir, csumtag)

        if os.path.exists(csumfile) and float(self.filetime) <= float(os.stat(csumfile)[-2]):
            csumo = open(csumfile, 'r')
            checksum = csumo.readline()
            csumo.close()

        else:
            checksum = misc.checksum(self.checksum_type, self.localpath)

            #  This is atomic cache creation via. rename, so we can have two
            # tasks using the same cachedir ... mash does this.
            try:
                (csumo, tmpfilename) = tempfile.mkstemp(dir=self._cachedir)
                csumo = os.fdopen(csumo, 'w', -1)
                csumo.write(checksum)
                csumo.close()
                #  tempfile forces 002 ... we want to undo that, so that users
                # can share the cache. BZ 833350.
                os.chmod(tmpfilename, 0666 ^ _b4rpm_oumask)
                os.rename(tmpfilename, csumfile)
            except:
                pass

        self._checksum = checksum
        self._checksums = [(self.checksum_type, checksum, 1)]

        return self._checksum

    # sqlite-direct dump code below here :-/

    def _sqlite_null(self, item):
        if not item:
            return None
        return item

    def do_primary_sqlite_dump(self, cur):
        """insert primary data in place, this assumes the tables exist"""
        if self.crp_reldir and self.localpath.startswith(self.crp_reldir):
            relpath = self.localpath.replace(self.crp_reldir, '')
            if relpath[0] == '/': relpath = relpath[1:]
        else:
            relpath = self.localpath

        p = (self.crp_packagenumber, self.checksum, self.name, self.arch,
            self.version, self.epoch, self.release, self.summary.strip(),
            self.description.strip(), self._sqlite_null(self.url), self.filetime,
            self.buildtime, self._sqlite_null(self.license),
            self._sqlite_null(self.vendor), self._sqlite_null(self.group),
            self._sqlite_null(self.buildhost), self._sqlite_null(self.sourcerpm),
            self.hdrstart, self.hdrend, self._sqlite_null(self.packager),
            self.packagesize, self.size, self.archivesize, relpath,
            self.crp_baseurl, self.checksum_type)

        q = """insert into packages values (?, ?, ?, ?, ?, ?,
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?, ?, ?, ?, ?,
               ?, ?, ?)"""

        # write out all of do_primary_sqlite as an executescript - work on the
        # quoting for pretty much any contingency - take from sqlutils.py
        #
        # e
        #p = None
        #q = """insert into packages values (%s, %s, %s, %s, """

        cur.execute(q, p)

        # provides, obsoletes, conflicts
        for pco in ('obsoletes', 'provides', 'conflicts'):
            thispco = []
            for (name, flag, (epoch, ver, rel)) in getattr(self, pco):
                thispco.append((name, flag, epoch, ver, rel, self.crp_packagenumber))

            q = "insert into %s values (?, ?, ?, ?, ?, ?)" % pco
            cur.executemany(q, thispco)

        # requires
        reqs = []
        for (name, flag, (epoch, ver, rel), pre) in self._requires_with_pre():
            if name.startswith('rpmlib('):
                continue
            pre_bool = 'FALSE'
            if pre == 1:
                pre_bool = 'TRUE'
            reqs.append((name, flag, epoch, ver,rel, self.crp_packagenumber, pre_bool))
        q = "insert into requires values (?, ?, ?, ?, ?, ?, ?)"
        cur.executemany(q, reqs)

        # files
        p = []
        for f in self._return_primary_files():
            p.append((f,))

        if p:
            q = "insert into files values (?, 'file', %s)" % self.crp_packagenumber
            cur.executemany(q, p)

        # dirs
        p = []
        for f in self._return_primary_dirs():
            p.append((f,))
        if p:
            q = "insert into files values (?, 'dir', %s)" % self.crp_packagenumber
            cur.executemany(q, p)


        # ghosts
        p = []
        for f in self._return_primary_files(list_of_files = self.returnFileEntries('ghost')):
            p.append((f,))
        if p:
            q = "insert into files values (?, 'ghost', %s)" % self.crp_packagenumber
            cur.executemany(q, p)



    def do_filelists_sqlite_dump(self, cur):
        """inserts filelists data in place, this assumes the tables exist"""
        # insert packagenumber + checksum into 'packages' table
        q = 'insert into packages values (?, ?)'
        p = (self.crp_packagenumber, self.checksum)

        cur.execute(q, p)

        # break up filelists and encode them
        dirs = {}
        for (filetype, files) in [('file', self.filelist), ('dir', self.dirlist),
                                  ('ghost', self.ghostlist)]:
            for filename in files:
                (dirname,filename) = (os.path.split(filename))
                if not dirs.has_key(dirname):
                    dirs[dirname] = {'files':[], 'types':[]}
                dirs[dirname]['files'].append(filename)
                dirs[dirname]['types'].append(filetype)

        # insert packagenumber|dir|files|types into files table
        p = []
        for (dirname,direc) in dirs.items():
            p.append((self.crp_packagenumber, dirname,
                 utils.encodefilenamelist(direc['files']),
                 utils.encodefiletypelist(direc['types'])))
        if p:
            q = 'insert into filelist values (?, ?, ?, ?)'
            cur.executemany(q, p)


    def do_other_sqlite_dump(self, cur):
        """inserts changelog data in place, this assumes the tables exist"""
        # insert packagenumber + checksum into 'packages' table
        q = 'insert into packages values (?, ?)'
        p = (self.crp_packagenumber, self.checksum)

        cur.execute(q, p)

        if self.changelog:
            q = 'insert into changelog ("pkgKey", "date", "author", "changelog") values (%s, ?, ?, ?)' % self.crp_packagenumber
            cur.executemany(q, self.changelog)


    def do_sqlite_dump(self, md_sqlite):
        """write the metadata out to the sqlite dbs"""
        self.do_primary_sqlite_dump(md_sqlite.primary_cursor)
        md_sqlite.pri_cx.commit()
        self.do_filelists_sqlite_dump(md_sqlite.filelists_cursor)
        md_sqlite.file_cx.commit()
        self.do_other_sqlite_dump(md_sqlite.other_cursor)
        md_sqlite.other_cx.commit()
