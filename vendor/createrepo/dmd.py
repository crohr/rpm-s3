#!/usr/bin/python

# dmd - Generate and apply deltas between repository metadata
#
# Copyright (C) 2007 James Bowes <jbowes@redhat.com>
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

import sys
from lxml.etree import parse, tostring, Element


class MdType(object):
    def __init__(self, namespace, rootelem):
        self.ns = "http://linux.duke.edu/metadata/%s" % namespace
        self.sns = "{%s}" % self.ns
        self.deltasns = "{http://linux.duke.edu/metadata/delta}"
        self.root = rootelem

    def get_pkg_id(self, pkg):
        return pkg.findtext(self.sns + "checksum")

    def make_hash(self, tree):
        pkgshash = {}
        for pkg in tree:
            pkgid = self.get_pkg_id(pkg)
            pkgshash[pkgid] = pkg

        return pkgshash

    def make_pkg_elem(self, pkgid, pkg):
        pkgelem = Element("package")
        pkgelem.set('name', pkg.findtext(self.sns + 'name'))
        pkgelem.set('arch', pkg.findtext(self.sns + 'arch'))
        pkgelem.set('pkgid', pkgid)
        verelem = pkg.find(self.sns + 'version')
        verelem.tag = "version"
        pkgelem.append(verelem)

        return pkgelem

    def diff_trees(self, oldtree, newtree):
        oldpkgs = oldtree.getroot().getchildren()
        newpkgs = newtree.getroot().getchildren()

        oldpkgshash = self.make_hash(oldpkgs)
        newpkgshash = self.make_hash(newpkgs)

        diff =  Element(self.root,
                nsmap = {None : self.ns,
                         "rpm" : "http://linux.duke.edu/metadata/rpm",
                         "delta" : "http://linux.duke.edu/metadata/delta"})
        additions = Element("delta:additions")
        diff.append(additions)
        removals = Element("delta:removals")

        diff.append(removals)

        for pkgid, pkg in newpkgshash.iteritems():
            if not oldpkgshash.has_key(pkgid):
                additions.append(pkg)

        for pkgid, pkg in oldpkgshash.iteritems():
            if not newpkgshash.has_key(pkgid):
                pkgelem = self.make_pkg_elem(pkgid, pkg)
                removals.append(pkgelem)

        diff.set("packages", str(len(removals) + len(additions)))

        print tostring(diff, pretty_print=True)

    def patch_tree(self, oldtree, deltatree):
        oldroot = oldtree.getroot()
        oldpkgs = oldroot.getchildren()

        oldpkgshash = self.make_hash(oldpkgs)

        additions = deltatree.find(self.deltasns + 'additions').getchildren()
        removals = deltatree.find(self.deltasns + 'removals').getchildren()

        for pkg in additions:
            pkgid = self.get_pkg_id(pkg)
            if oldpkgshash.has_key(pkgid):
                print >> sys.stderr, "Package %s already exists" % pkgid
                sys.exit(1)
            oldroot.append(pkg)

        for pkg in removals:
            pkgid = pkg.get('pkgid')
            if not oldpkgshash.has_key(pkgid):
                print >> sys.stderr, "Package %s does not exist" % pkgid
                sys.exit(1)
            oldroot.remove(oldpkgshash[pkgid])

        oldcount = int(oldroot.get('packages'))
        newcount = oldcount + len(additions) - len(removals)
        oldroot.set('packages', str(newcount))
        print tostring(oldtree, pretty_print=True)


class OtherMdType(MdType):
    def get_pkg_id(self, pkg):
        return pkg.get('pkgid')

    def make_pkg_elem(self, pkgid, pkg):
        pkgelem = Element("package")
        pkgelem.set('name', pkg.get('name'))
        pkgelem.set('arch', pkg.get('arch'))
        pkgelem.set('pkgid', pkgid)
        verelem = pkg.find(self.sns + 'version')
        verelem.tag = "version"

        return pkgelem


mdtypeinfo = {
        'primary' : MdType('common', 'metadata'),
        'filelists' : OtherMdType('filelists', 'filelists'),
        'other' : OtherMdType('other', 'other'),
        }


def usage(progname):
    print "usage: %s [diff|patch] MDTYPE FILE1 FILE2" % progname
    sys.exit()

def main(args):
    if len(args) != 5:
        usage(args[0])
    if args[1] not in ('diff', 'patch'):
        usage(args[0])
    if args[2] not in ('primary', 'filelists', 'other'):
        usage(args[0])

    oldtree = parse(args[3])
    newtree = parse(args[4])

    if args[1] == 'diff':
        mdtypeinfo[args[2]].diff_trees(oldtree, newtree)
    else:
        mdtypeinfo[args[2]].patch_tree(oldtree, newtree)

if __name__ == "__main__":
    main(sys.argv)
