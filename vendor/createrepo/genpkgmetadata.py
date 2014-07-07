#!/usr/bin/python -t
# primary functions and glue for generating the repository metadata
#

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
# Copyright 2004 Duke University
# Portions Copyright 2009  Red Hat, Inc -
# written by seth vidal skvidal at fedoraproject.org

import os
import sys
import re
from optparse import OptionParser,SUPPRESS_HELP
import time
import errno

import createrepo
from createrepo import MDError
from createrepo.utils import errorprint, _
import yum.misc


def parse_args(args, conf):
    """
       Parse the command line args. return a config object.
       Sanity check all the things being passed in.
    """

    def_workers = os.nice(0)
    if def_workers > 0:
        def_workers = 1 # We are niced, so just use a single worker.
    else:
        def_workers = 0 # zoooom....

    _def   = yum.misc._default_checksums[0]
    _avail = yum.misc._available_checksums
    parser = OptionParser(version = "createrepo %s" % createrepo.__version__)
    # query options
    parser.add_option("-q", "--quiet", default=False, action="store_true",
        help="output nothing except for serious errors")
    parser.add_option("-v", "--verbose", default=False, action="store_true",
        help="output more debugging info.")
    parser.add_option("--profile", default=False, action="store_true",
        help="output timing/profile info.")
    parser.add_option("-x", "--excludes", default=[], action="append",
        help="files to exclude")
    parser.add_option("--basedir", default=os.getcwd(),
        help="basedir for path to directories")
    parser.add_option("-u", "--baseurl", default=None,
        help="baseurl to append on all files")
    parser.add_option("-g", "--groupfile", default=None,
        help="path to groupfile to include in metadata")
    parser.add_option("-s", "--checksum", default=_def, dest='sumtype',
        help="specify the checksum type to use (default: %s)" % _def)
    parser.add_option("-p", "--pretty", default=False, action="store_true",
        help="make sure all xml generated is formatted")
    parser.add_option("-c", "--cachedir", default=None,
        help="set path to cache dir")
    parser.add_option("-C", "--checkts", default=False, action="store_true",
        help="check timestamps on files vs the metadata to see " \
           "if we need to update")
    parser.add_option("-d", "--database", default=True, action="store_true",
        help="create sqlite database files: now default, see --no-database to disable")
    parser.add_option("--no-database", default=False, dest="nodatabase", action="store_true",
        help="do not create sqlite dbs of metadata")
    # temporarily disabled
    #parser.add_option("--database-only", default=False, action="store_true",
    #  dest='database_only',
    #  help="Only make the sqlite databases - does not work with --update, yet")
    parser.add_option("--update", default=False, action="store_true",
        help="use the existing repodata to speed up creation of new")
    parser.add_option("--update-md-path", default=None, dest='update_md_path',
        help="use the existing repodata  for --update from this path")
    parser.add_option("--skip-stat", dest='skip_stat', default=False,
        help="skip the stat() call on a --update, assumes if the file" \
             "name is the same then the file is still the same " \
             "(only use this if you're fairly trusting or gullible)",
        action="store_true")
    parser.add_option("--split", default=False, action="store_true",
        help="generate split media")
    parser.add_option("-i", "--pkglist", default=None,
        help="use only the files listed in this file from the " \
             "directory specified")
    parser.add_option("-n", "--includepkg", default=[], action="append",
        help="add this pkg to the list - can be specified multiple times")
    parser.add_option("-o", "--outputdir", default=None,
        help="<dir> = optional directory to output to")
    parser.add_option("-S", "--skip-symlinks", dest="skip_symlinks",
        default=False, action="store_true", help="ignore symlinks of packages")
    parser.add_option("--changelog-limit", dest="changelog_limit",
        default=None, help="only import the last N changelog entries")
    parser.add_option("--unique-md-filenames", dest="unique_md_filenames",
        help="include the file's checksum in the filename, helps with proxies (default)",
        default=True, action="store_true")
    parser.add_option("--simple-md-filenames", dest="unique_md_filenames",
        help="do not include the file's checksum in the filename",
        action="store_false")
    parser.add_option("--retain-old-md", default=0, type='int', dest='retain_old_md',
        help="keep around the latest (by timestamp) N copies of the old repodata")
    parser.add_option("--distro", default=[], action="append",
        help="distro tag and optional cpeid: --distro" "'cpeid,textname'")
    parser.add_option("--content", default=[], dest='content_tags',
        action="append", help="tags for the content in the repository")
    parser.add_option("--repo", default=[], dest='repo_tags', 
        action="append", help="tags to describe the repository itself")
    parser.add_option("--revision", default=None,
        help="user-specified revision for this repository")
    parser.add_option("--deltas", default=False, action="store_true",
        help="create delta rpms and metadata")
    parser.add_option("--oldpackagedirs", default=[], dest="oldpackage_paths",
        action="append", help="paths to look for older pkgs to delta against")
    parser.add_option("--num-deltas", default=1, dest='num_deltas', type='int',
        help="the number of older versions to make deltas against")
    parser.add_option("--read-pkgs-list", default=None, dest='read_pkgs_list',
        help="output the paths to the pkgs actually read useful with --update")
    parser.add_option("--max-delta-rpm-size", default=100000000,
        dest='max_delta_rpm_size', type='int',
        help="max size of an rpm that to run deltarpm against (in bytes)")
    parser.add_option("--workers", default=def_workers,
        dest='workers', type='int',
        help="number of workers to spawn to read rpms")
    parser.add_option("--xz", default=False,
        action="store_true",
        help=SUPPRESS_HELP)
    parser.add_option("--compress-type", default='compat', dest="compress_type",
        help="which compression type to use")
        
    
    (opts, argsleft) = parser.parse_args(args)
    if len(argsleft) > 1 and not opts.split:
        errorprint(_('Error: Only one directory allowed per run.'))
        parser.print_usage()
        sys.exit(1)

    elif len(argsleft) == 0:
        errorprint(_('Error: Must specify a directory to index.'))
        parser.print_usage()
        sys.exit(1)

    else:
        directories = argsleft

    if opts.workers >= 128:
        errorprint(_('Warning: More than 128 workers is a lot. Limiting.'))
        opts.workers = 128
    if opts.sumtype == 'sha1':
        errorprint(_('Warning: It is more compatible to use sha instead of sha1'))

    if opts.sumtype != 'sha' and opts.sumtype not in _avail:
        errorprint(_('Error: Checksum %s not available (sha, %s)') %
                   (opts.sumtype, ", ".join(sorted(_avail))))
        sys.exit(1)

    if opts.split and opts.checkts:
        errorprint(_('--split and --checkts options are mutually exclusive'))
        sys.exit(1)

    if opts.nodatabase:
        opts.database = False
    
    # xz is just a shorthand for compress_type
    if opts.xz and opts.compress_type == 'compat':
        opts.compress_type='xz'
        
        
    # let's switch over to using the conf object - put all the opts into it
    for opt in parser.option_list:
        if opt.dest is None: # this is fairly silly
            continue
        # if it's not set, take the default from the base class
        if getattr(opts, opt.dest) is None:
            continue
        setattr(conf, opt.dest, getattr(opts, opt.dest))

    directory = directories[0]
    conf.directory = directory
    conf.directories = directories

    # distro tag parsing

    for spec in opts.distro:
        if spec.find(',') == -1:
            conf.distro_tags.append((None, spec))
        else:
            splitspec = spec.split(',')
            conf.distro_tags.append((splitspec[0], splitspec[1]))

    lst = []
    if conf.pkglist:
        pfo = open(conf.pkglist, 'r')
        for line in pfo.readlines():
            line = line.strip()
            if re.match('^\s*\#.*', line) or re.match('^\s*$', line):
                continue
            lst.append(line)
        pfo.close()

    conf.pkglist = lst

    if conf.includepkg:
        conf.pkglist.extend(conf.includepkg)

    if conf.changelog_limit: # make sure it is an int, not a string
        conf.changelog_limit = int(conf.changelog_limit)

    return conf

class MDCallBack(object):
    """cli callback object for createrepo"""
    def __init__(self):
        self.__show_progress = os.isatty(1)

    def errorlog(self, thing):
        """error log output"""
        print >> sys.stderr, thing

    def log(self, thing):
        """log output"""
        print thing

    def progress(self, item, current, total):
        """progress bar"""
        
        if not self.__show_progress:
            return
        beg = "%*d/%d - " % (len(str(total)), current, total)
        left = 80 - len(beg)
        sys.stdout.write("\r%s%-*.*s" % (beg, left, left, item))
        sys.stdout.flush()

def main(args):
    """createrepo from cli main flow"""
    try:
        os.getcwd()
    except OSError, e:
        if e.errno != errno.ENOENT: raise
        print ('No getcwd() access in current directory.')
        sys.exit(1)
    start_st = time.time()
    conf = createrepo.MetaDataConfig()
    conf = parse_args(args, conf)
    if conf.profile:
        print ('start time: %0.3f' % (time.time() - start_st))

    mid_st = time.time()
    try:
        if conf.split:
            mdgen = createrepo.SplitMetaDataGenerator(config_obj=conf,
                                                      callback=MDCallBack())
        else:
            mdgen = createrepo.MetaDataGenerator(config_obj=conf,
                                                 callback=MDCallBack())
            if mdgen.checkTimeStamps():
                if mdgen.conf.verbose:
                    print _('repo is up to date')
                mdgen._cleanup_tmp_repodata_dir()
                sys.exit(0)

        if conf.profile:
            print ('mid time: %0.3f' % (time.time() - mid_st))

        pm_st = time.time()
        mdgen.doPkgMetadata()
        if conf.profile:
            print ('pm time: %0.3f' % (time.time() - pm_st))
        rm_st = time.time()
        mdgen.doRepoMetadata()
        if conf.profile:
            print ('rm time: %0.3f' % (time.time() - rm_st))
        fm_st = time.time()
        mdgen.doFinalMove()
        if conf.profile:
            print ('fm time: %0.3f' % (time.time() - fm_st))


    except MDError, errormsg:
        errorprint(_('%s') % errormsg)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == 'profile':
            import hotshot
            p = hotshot.Profile(os.path.expanduser("~/createrepo.prof"))
            p.run('main(sys.argv[2:])')
            p.close()
        else:
            main(sys.argv[1:])
    else:
        main(sys.argv[1:])
