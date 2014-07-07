#!/usr/bin/python -tt
# util functions for deltarpms
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
# copyright 2009 - Red Hat

import os.path
import commands
from yum import misc
import deltarpm
from utils import MDError

class DeltaRPMPackage:
    """each drpm is one object, you pass it a drpm file
       it opens the file, and pulls the information out in bite-sized chunks :)
    """

    mode_cache = {}

    def __init__(self, po, basedir, filename):
        try:
            stats = os.stat(os.path.join(basedir, filename))
            self.size = stats[6]
            self.mtime = stats[8]
            del stats
        except OSError, e:
            raise MDError, "Error Stat'ing file %s%s" % (basedir, filename)
        self.csum_type = 'sha256'
        self.relativepath = filename
        self.po  = po

        fd = os.open(self.po.localpath, os.O_RDONLY)
        os.lseek(fd, 0, 0)
        fo = os.fdopen(fd, 'rb')
        self.csum = misc.checksum(self.csum_type, fo)
        del fo
        del fd
        self._getDRPMInfo(os.path.join(basedir, filename))

    def _stringToNEVR(self, string):
        i = string.rfind("-", 0, string.rfind("-")-1)
        name = string[:i]
        (epoch, ver, rel) = self._stringToVersion(string[i+1:])
        return (name, epoch, ver, rel)

    def _getLength(self, in_data):
        length = 0
        for val in in_data:
            length = length * 256
            length += ord(val)
        return length

    def _getDRPMInfo(self, filename):
        d = deltarpm.readDeltaRPM(filename)
        self.oldnevrstring = d['old_nevr']
        self.oldnevr = self._stringToNEVR(d['old_nevr'])
        self.sequence = d['seq']

    def _stringToVersion(self, strng):
        i = strng.find(':')
        if i != -1:
            epoch = strng[:i]
        else:
            epoch = '0'
        j = strng.find('-')
        if j != -1:
            if strng[i + 1:j] == '':
                version = None
            else:
                version = strng[i + 1:j]
            release = strng[j + 1:]
        else:
            if strng[i + 1:] == '':
                version = None
            else:
                version = strng[i + 1:]
            release = None
        return (epoch, version, release)

    def xml_dump_metadata(self):
        """takes an xml doc object and a package metadata entry node, populates a
           package node with the md information"""

        (oldname, oldepoch, oldver, oldrel) = self.oldnevr
        sequence = "%s-%s" % (self.oldnevrstring, self.sequence)

        delta_tag = """    <delta oldepoch="%s" oldversion="%s" oldrelease="%s">
      <filename>%s</filename>
      <sequence>%s</sequence>
      <size>%s</size>
      <checksum type="%s">%s</checksum>
    </delta>\n""" % (oldepoch, oldver, oldrel, self.relativepath, sequence,
                    self.size, self.csum_type, self.csum)
        return delta_tag

def create_drpm(old_pkg, new_pkg, destdir):
    """make a drpm file, if possible. returns None if nothing could
       be created"""
    drpmfn = '%s-%s-%s_%s-%s.%s.drpm' % (old_pkg.name, old_pkg.ver,
                            old_pkg.release, new_pkg.ver, new_pkg.release,
                            old_pkg.arch)
    delta_rpm_path  = os.path.join(destdir, drpmfn)
    delta_command = '/usr/bin/makedeltarpm %s %s %s' % (old_pkg.localpath,
                                                        new_pkg.localpath,
                                                        delta_rpm_path)
    if not os.path.exists(delta_rpm_path):
        #TODO - check/verify the existing one a bit?
        (code, out) = commands.getstatusoutput(delta_command)
        if code:
            print "Error genDeltaRPM for %s: exitcode was %s - Reported Error: %s" % (old_pkg.name, code, out)
            return None

    return delta_rpm_path
