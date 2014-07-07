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
# Copyright 2008  Red Hat, Inc - written by skvidal at fedoraproject.org

# merge repos from arbitrary repo urls

import sys
import createrepo.merge
from createrepo.utils import MDError
from optparse import OptionParser

#TODO:
# excludes?
# handle content/distro tags
# support revision?


def parse_args(args):
    """Parse our opts/args"""
    usage = """
    mergerepo: take 2 or more repositories and merge their metadata into a new repo

    mergerepo --repo=url --repo=url --outputdir=/some/path"""

    parser = OptionParser(version = "mergerepo 0.1", usage=usage)
    # query options
    parser.add_option("-r", "--repo", dest='repos', default=[], action="append",
                      help="repo url")
    parser.add_option("-a", "--archlist", default=[], action="append",
                      help="Defaults to all arches - otherwise specify arches")
    parser.add_option("-d", "--database", default=True, action="store_true")
    parser.add_option( "--no-database", default=False, action="store_true", dest="nodatabase")
    parser.add_option("-o", "--outputdir", default=None,
                      help="Location to create the repository")
    parser.add_option("", "--nogroups", default=False, action="store_true",
                      help="Do not merge group(comps) metadata")
    parser.add_option("", "--noupdateinfo", default=False, action="store_true",
                      help="Do not merge updateinfo metadata")
    parser.add_option("--compress-type", default=None, dest="compress_type",
                      help="which compression type to use")
                      
    (opts, argsleft) = parser.parse_args(args)

    if len(opts.repos) < 2:
        parser.print_usage()
        sys.exit(1)

    # sort out the comma-separated crap we somehow inherited.
    archlist = []
    for archs in opts.archlist:
        for arch in archs.split(','):
            archlist.append(arch)

    opts.archlist = archlist

    return opts

def main(args):
    """main"""
    opts = parse_args(args)
    rmbase = createrepo.merge.RepoMergeBase(opts.repos)
    if opts.archlist:
        rmbase.archlist = opts.archlist
    if opts.outputdir:
        rmbase.outputdir = opts.outputdir
    if opts.nodatabase:
        rmbase.mdconf.database = False
    if opts.nogroups:
        rmbase.groups = False
    if opts.noupdateinfo:
        rmbase.updateinfo = False
    if opts.compress_type:
        rmbase.mdconf.compress_type = opts.compress_type
    try:
        rmbase.merge_repos()
        rmbase.write_metadata()
    except MDError, e:
        print >> sys.stderr, "Could not merge repos: %s" % e
        sys.exit(1)
        
if __name__ == "__main__":
    main(sys.argv[1:])
