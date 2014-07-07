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
# Copyright 2009  Red Hat, Inc -
# written by seth vidal skvidal at fedoraproject.org

import os
import sys
import fnmatch
import time
import yumbased
import shutil
from  bz2 import BZ2File
from urlgrabber import grabber
import tempfile
import stat
import fcntl
import subprocess
from select import select

from yum import misc, Errors
from yum.repoMDObject import RepoMD, RepoData
from yum.sqlutils import executeSQL
from yum.packageSack import MetaSack
from yum.packages import YumAvailablePackage

import rpmUtils.transaction
from utils import _, errorprint, MDError, lzma, _available_compression
import readMetadata
try:
    import sqlite3 as sqlite
except ImportError:
    import sqlite

try:
    import sqlitecachec
except ImportError:
    pass

from utils import _gzipOpen, compressFile, compressOpen, checkAndMakeDir, GzipFile, \
                  checksum_and_rename, split_list_into_equal_chunks
from utils import num_cpus_online
import deltarpms

__version__ = '0.9.9'


class MetaDataConfig(object):
    def __init__(self):
        self.quiet = False
        self.verbose = False
        self.profile = False
        self.excludes = []
        self.baseurl = None
        self.groupfile = None
        self.sumtype = 'sha256'
        self.pretty = False
        self.cachedir = None
        self.use_cache = False
        self.basedir = os.getcwd()
        self.checkts = False
        self.split = False
        self.update = False
        self.deltas = False # do the deltarpm thing
        # where to put the .drpms - defaults to 'drpms' inside 'repodata'
        self.deltadir = None
        self.delta_relative = 'drpms/'
        self.oldpackage_paths = [] # where to look for the old packages -
        self.deltafile = 'prestodelta.xml'
        self.num_deltas = 1 # number of older versions to delta (max)
        self.max_delta_rpm_size = 100000000
        self.update_md_path = None
        self.skip_stat = False
        self.database = True
        self.outputdir = None
        self.file_patterns = ['.*bin\/.*', '^\/etc\/.*', '^\/usr\/lib\/sendmail$']
        self.dir_patterns = ['.*bin\/.*', '^\/etc\/.*']
        self.skip_symlinks = False
        self.pkglist = []
        self.database_only = False
        self.primaryfile = 'primary.xml'
        self.filelistsfile = 'filelists.xml'
        self.otherfile = 'other.xml'
        self.repomdfile = 'repomd.xml'
        self.tempdir = '.repodata'
        self.finaldir = 'repodata'
        self.olddir = '.olddata'
        self.mdtimestamp = 0
        self.directory = None
        self.directories = []
        self.changelog_limit = None # needs to be an int or None
        self.unique_md_filenames = True
        self.additional_metadata = {} # dict of 'type':'filename'
        self.revision = str(int(time.time()))
        self.content_tags = [] # flat list of strings (like web 2.0 tags)
        self.distro_tags = []# [(cpeid(None allowed), human-readable-string)]
        self.repo_tags = []# strings, forwhatever they are worth
        self.read_pkgs_list = None # filepath/name to write out list of pkgs
                                   # read in this run of createrepo
        self.collapse_glibc_requires = True
        self.worker_cmd = '/usr/share/createrepo/worker.py'
        #self.worker_cmd = './worker.py' # helpful when testing
        self.retain_old_md = 0
        self.compress_type = 'compat'

        
class SimpleMDCallBack(object):
    def errorlog(self, thing):
        print >> sys.stderr, thing

    def log(self, thing):
        print thing

    def progress(self, item, current, total):
        sys.stdout.write('\r' + ' ' * 80)
        sys.stdout.write("\r%d/%d - %s" % (current, total, item))
        sys.stdout.flush()


class MetaDataGenerator:
    def __init__(self, config_obj=None, callback=None):
        self.conf = config_obj
        if config_obj == None:
            self.conf = MetaDataConfig()
        if not callback:
            self.callback = SimpleMDCallBack()
        else:
            self.callback = callback


        self.ts = rpmUtils.transaction.initReadOnlyTransaction()
        self.pkgcount = 0
        self.current_pkg = 0
        self.files = []
        self.rpmlib_reqs = {}
        self.read_pkgs = []
        self.compat_compress = False

        if not self.conf.directory and not self.conf.directories:
            raise MDError, "No directory given on which to run."
        
        if self.conf.compress_type == 'compat':
            self.compat_compress = True
            self.conf.compress_type = None
            
        if not self.conf.compress_type:
            self.conf.compress_type = 'gz'
        
        if self.conf.compress_type not in utils._available_compression:
            raise MDError, "Compression %s not available: Please choose from: %s" \
                 % (self.conf.compress_type, ', '.join(utils._available_compression))
            
            
        if not self.conf.directories: # just makes things easier later
            self.conf.directories = [self.conf.directory]
        if not self.conf.directory: # ensure we have both in the config object
            self.conf.directory = self.conf.directories[0]

        # the cachedir thing:
        if self.conf.cachedir:
            self.conf.use_cache = True

        # this does the dir setup we need done
        self._parse_directory()
        self._test_setup_dirs()

    def _parse_directory(self):
        """pick up the first directory given to us and make sure we know
           where things should go"""
        if os.path.isabs(self.conf.directory):
            self.conf.basedir = os.path.dirname(self.conf.directory)
            self.conf.relative_dir = os.path.basename(self.conf.directory)
        else:
            self.conf.basedir = os.path.realpath(self.conf.basedir)
            self.conf.relative_dir = self.conf.directory

        self.package_dir = os.path.join(self.conf.basedir,
                                        self.conf.relative_dir)

        if not self.conf.outputdir:
            self.conf.outputdir = os.path.join(self.conf.basedir,
                                               self.conf.relative_dir)

    def _test_setup_dirs(self):
        # start the sanity/stupidity checks
        for mydir in self.conf.directories:
            if os.path.isabs(mydir):
                testdir = mydir
            else:
                if mydir.startswith('../'):
                    testdir = os.path.realpath(mydir)
                else:
                    testdir = os.path.join(self.conf.basedir, mydir)

            if not os.path.exists(testdir):
                raise MDError, _('Directory %s must exist') % mydir

            if not os.path.isdir(testdir):
                raise MDError, _('%s must be a directory') % mydir

        if not os.access(self.conf.outputdir, os.W_OK):
            raise MDError, _('Directory %s must be writable.') % self.conf.outputdir

        temp_output = os.path.join(self.conf.outputdir, self.conf.tempdir)
        if not checkAndMakeDir(temp_output):
            raise MDError, _('Cannot create/verify %s') % temp_output

        temp_final = os.path.join(self.conf.outputdir, self.conf.finaldir)
        if not checkAndMakeDir(temp_final):
            raise MDError, _('Cannot create/verify %s') % temp_final

        if self.conf.database:
            # do flock test on temp_final, temp_output
            # if it fails raise MDError
            for direc in [temp_final, temp_output]:
                f = open(direc + '/locktest', 'w')
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                except (OSError, IOError), e:
                    raise MDError, _("Could not create exclusive lock in %s and sqlite database generation enabled. Is this path on nfs? Is your lockd running?") % direc
                else:
                    os.unlink(direc + '/locktest')
                
        if self.conf.deltas:
            temp_delta = os.path.join(self.conf.outputdir,
                                      self.conf.delta_relative)
            if not checkAndMakeDir(temp_delta):
                raise MDError, _('Cannot create/verify %s') % temp_delta
            self.conf.deltadir = temp_delta

        if os.path.exists(os.path.join(self.conf.outputdir, self.conf.olddir)):
            raise MDError, _('Old data directory exists, please remove: %s') % self.conf.olddir

        # make sure we can write to where we want to write to:
        # and pickup the mdtimestamps while we're at it
        direcs = ['tempdir' , 'finaldir']
        if self.conf.deltas:
            direcs.append('deltadir')

        for direc in direcs:
            filepath = os.path.join(self.conf.outputdir, getattr(self.conf,
                                                                 direc))
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    raise MDError, _('error in must be able to write to metadata dir:\n  -> %s') % filepath

                if self.conf.checkts:
                    # checking for repodata/repomd.xml - not just the data dir
                    rxml = filepath + '/repomd.xml'
                    if os.path.exists(rxml):
                        timestamp = os.path.getctime(rxml)
                        if timestamp > self.conf.mdtimestamp:
                            self.conf.mdtimestamp = timestamp

        if self.conf.groupfile:
            a = self.conf.groupfile
            if self.conf.split:
                a = os.path.join(self.package_dir, self.conf.groupfile)
            elif not os.path.isabs(a):
                a = os.path.join(self.package_dir, self.conf.groupfile)

            if not os.path.exists(a):
                raise MDError, _('Error: groupfile %s cannot be found.' % a)

            self.conf.groupfile = a

        if self.conf.cachedir:
            a = self.conf.cachedir
            if not os.path.isabs(a):
                a = os.path.join(self.conf.outputdir, a)
            if not checkAndMakeDir(a):
                raise MDError, _('Error: cannot open/write to cache dir %s' % a)

            self.conf.cachedir = a


    def _os_path_walk(self, top, func, arg):
        """Directory tree walk with callback function.
         copy of os.path.walk, fixes the link/stating problem
         """

        try:
            names = os.listdir(top)
        except os.error:
            return
        func(arg, top, names)
        for name in names:
            name = os.path.join(top, name)
            if os.path.isdir(name):
                self._os_path_walk(name, func, arg)
    def getFileList(self, directory, ext):
        """Return all files in path matching ext, store them in filelist,
        recurse dirs. Returns a list object"""

        extlen = len(ext)

        def extension_visitor(filelist, dirname, names):
            for fn in names:
                fn = os.path.join(dirname, fn)
                if os.path.isdir(fn):
                    continue
                if self.conf.skip_symlinks and os.path.islink(fn):
                    continue
                elif fn[-extlen:].lower() == '%s' % (ext):
                    filelist.append(fn[len(startdir):])

        filelist = []
        startdir = directory + '/'
        self._os_path_walk(startdir, extension_visitor, filelist)
        return filelist

    def errorlog(self, thing):
        """subclass this if you want something different...."""
        errorprint(thing)

    def checkTimeStamps(self):
        """check the timestamp of our target dir. If it is not newer than
           the repodata return False, else True"""
        if self.conf.checkts and self.conf.mdtimestamp:
            dn = os.path.join(self.conf.basedir, self.conf.directory)
            files = self.getFileList(dn, '.rpm')
            files = self.trimRpms(files)
            for f in files:
                fn = os.path.join(self.conf.basedir, self.conf.directory, f)
                if not os.path.exists(fn):
                    self.callback.errorlog(_('cannot get to file: %s') % fn)
                if os.path.getctime(fn) > self.conf.mdtimestamp:
                    return False

            return True

        return False

    def trimRpms(self, files):
        badrpms = []
        for rpm_file in files:
            for glob in self.conf.excludes:
                if fnmatch.fnmatch(rpm_file, glob):
                    if rpm_file not in badrpms:
                        badrpms.append(rpm_file)
        for rpm_file in badrpms:
            if rpm_file in files:
                files.remove(rpm_file)
        return files

    def _setup_old_metadata_lookup(self):
        """sets up the .oldData object for handling the --update call. Speeds
           up generating updates for new metadata"""
        #FIXME - this only actually works for single dirs. It will only
        # function for the first dir passed to --split, not all of them
        # this needs to be fixed by some magic in readMetadata.py
        # using opts.pkgdirs as a list, I think.
        if self.conf.update:
            #build the paths
            opts = {
                'verbose' : self.conf.verbose,
                'pkgdir'  : os.path.normpath(self.package_dir)
            }

            if self.conf.skip_stat:
                opts['do_stat'] = False

            if self.conf.update_md_path:
                norm_u_md_path = os.path.normpath(self.conf.update_md_path)
                u_md_repodata_path  = norm_u_md_path + '/repodata'
                if not os.path.exists(u_md_repodata_path):
                    msg = _('Warning: could not open update_md_path: %s') %  u_md_repodata_path
                    self.callback.errorlog(msg)
                old_repo_path = os.path.normpath(norm_u_md_path)
            else:
                old_repo_path = self.conf.outputdir

            #and scan the old repo
            self.oldData = readMetadata.MetadataIndex(old_repo_path, opts)

    def _setup_grabber(self):
        if not hasattr(self, '_grabber'):
            self._grabber = grabber.URLGrabber()

        return self._grabber

    grabber = property(fget = lambda self: self._setup_grabber())


    def doPkgMetadata(self):
        """all the heavy lifting for the package metadata"""
        if self.conf.update:
            self._setup_old_metadata_lookup()
        # rpms we're going to be dealing with
        if self.conf.pkglist:
            packages = self.conf.pkglist
        else:
            packages = self.getFileList(self.package_dir, '.rpm')

        if not isinstance(packages, MetaSack):
            packages = self.trimRpms(packages)
        self.pkgcount = len(packages)
        try:
            self.openMetadataDocs()
            self.writeMetadataDocs(packages)
            self.closeMetadataDocs()
        except (IOError, OSError), e:
            raise MDError, _('Cannot access/write repodata files: %s') % e


    def openMetadataDocs(self):
        if self.conf.database_only:
            self.setup_sqlite_dbs()
        else:
            self.primaryfile = self._setupPrimary()
            self.flfile = self._setupFilelists()
            self.otherfile = self._setupOther()
        if self.conf.deltas:
            self.deltafile = self._setupDelta()

    def _setupPrimary(self):
        # setup the primary metadata file
        # FIXME - make this be  conf.compress_type once y-m-p is fixed
        fpz = self.conf.primaryfile + '.' + 'gz'
        primaryfilepath = os.path.join(self.conf.outputdir, self.conf.tempdir,
                                       fpz)
        fo = compressOpen(primaryfilepath, 'w', 'gz')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<metadata xmlns="http://linux.duke.edu/metadata/common"' \
            ' xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="%s">' %
                       self.pkgcount)
        return fo

    def _setupFilelists(self):
        # setup the filelist file
        # FIXME - make this be  conf.compress_type once y-m-p is fixed        
        fpz = self.conf.filelistsfile + '.' + 'gz'
        filelistpath = os.path.join(self.conf.outputdir, self.conf.tempdir,
                                    fpz)
        fo = compressOpen(filelistpath, 'w', 'gz')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<filelists xmlns="http://linux.duke.edu/metadata/filelists"' \
                 ' packages="%s">' % self.pkgcount)
        return fo

    def _setupOther(self):
        # setup the other file
        # FIXME - make this be  conf.compress_type once y-m-p is fixed        
        fpz = self.conf.otherfile + '.' + 'gz'
        otherfilepath = os.path.join(self.conf.outputdir, self.conf.tempdir,
                                     fpz)
        fo = compressOpen(otherfilepath, 'w', 'gz')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<otherdata xmlns="http://linux.duke.edu/metadata/other"' \
                 ' packages="%s">' %
                       self.pkgcount)
        return fo

    def _setupDelta(self):
        # setup the other file
        fpz = self.conf.deltafile + '.' + self.conf.compress_type        
        deltafilepath = os.path.join(self.conf.outputdir, self.conf.tempdir,
                                     fpz)
        fo = compressOpen(deltafilepath, 'w', self.conf.compress_type)
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<prestodelta>\n')
        return fo


    def read_in_package(self, rpmfile, pkgpath=None, reldir=None):
        """rpmfile == relative path to file from self.packge_dir"""
        baseurl = self.conf.baseurl

        if not pkgpath:
            pkgpath = self.package_dir

        if not rpmfile.strip():
            raise MDError, "Blank filename passed in, skipping"

        if rpmfile.find("://") != -1:

            if not hasattr(self, 'tempdir'):
                self.tempdir = tempfile.mkdtemp()

            pkgname = os.path.basename(rpmfile)
            baseurl = os.path.dirname(rpmfile)
            reldir = self.tempdir
            dest = os.path.join(self.tempdir, pkgname)
            if not self.conf.quiet:
                self.callback.log('\nDownloading %s' % rpmfile)
            try:
                rpmfile = self.grabber.urlgrab(rpmfile, dest)
            except grabber.URLGrabError, e:
                raise MDError, "Unable to retrieve remote package %s: %s" % (
                                                                     rpmfile, e)


        else:
            rpmfile = '%s/%s' % (pkgpath, rpmfile)

        external_data = { '_cachedir': self.conf.cachedir,
                          '_baseurl': baseurl,
                          '_reldir': reldir,
                          '_packagenumber': self.current_pkg,
                          '_collapse_libc_requires':self.conf.collapse_glibc_requires,
                          }
                        
        try:
            po = yumbased.CreateRepoPackage(self.ts, rpmfile,
                                            sumtype=self.conf.sumtype,
                                            external_data = external_data)
        except Errors.MiscError, e:
            raise MDError, "Unable to open package: %s" % e

        for r in po.requires_print:
            if r.startswith('rpmlib('):
                self.rpmlib_reqs[r] = 1

        if po.checksum in (None, ""):
            raise MDError, "No Package ID found for package %s, not going to" \
                           " add it" % po

        return po

    def writeMetadataDocs(self, pkglist=[], pkgpath=None):

        if not pkglist:
            pkglist = self.conf.pkglist

        if not pkgpath:
            directory = self.conf.directory
        else:
            directory = pkgpath

        # for worker/forked model
        # iterate the pkglist - see which ones are handled by --update and let them
        # go on their merry way
        
        newpkgs = []
        keptpkgs = []
        if self.conf.update:
            # if we're in --update mode then only act on the new/changed pkgs
            for pkg in pkglist:
                self.current_pkg += 1

                #see if we can pull the nodes from the old repo
                #print self.oldData.basenodes.keys()
                old_pkg = pkg
                if pkg.find("://") != -1:
                    old_pkg = os.path.basename(pkg)
                old_po = self.oldData.getNodes(old_pkg)
                if old_po: # we have a match in the old metadata
                    if self.conf.verbose:
                        self.callback.log(_("Using data from old metadata for %s")
                                            % pkg)
                    keptpkgs.append((pkg, old_po))

                    #FIXME - if we're in update and we have deltas enabled
                    # check the presto data for this pkg and write its info back out
                    # to our deltafile
                    continue
                else:
                    newpkgs.append(pkg)
        else:
            newpkgs = pkglist

        # setup our reldir
        if not pkgpath:
            reldir = os.path.join(self.conf.basedir, directory)
        else:
            reldir = pkgpath

        # filter out those pkgs which are not files - but are pkgobjects
        pkgfiles = []
        for pkg in newpkgs:
            po = None
            if isinstance(pkg, YumAvailablePackage):
                po = pkg
                self.read_pkgs.append(po.localPkg())

            # if we're dealing with remote pkgs - pitch it over to doing
            # them one at a time, for now. 
            elif pkg.find('://') != -1:
                po = self.read_in_package(pkg, pkgpath=pkgpath, reldir=reldir)
                self.read_pkgs.append(pkg)
            
            if po:
                keptpkgs.append((pkg, po))
                continue
                
            pkgfiles.append(pkg)

        keptpkgs.sort(reverse=True)
        # keptkgs is a list of (filename, po), pkgfiles is a list if filenames.
        # Need to write them in sorted(filename) order.  We loop over pkgfiles,
        # inserting keptpkgs in right spots (using the upto argument).
        def save_keptpkgs(upto):
            while keptpkgs and (upto is None or keptpkgs[-1][0] < upto):
                filename, po = keptpkgs.pop()
                # reset baseurl in the old pkg
                po.basepath = self.conf.baseurl
                self.primaryfile.write(po.xml_dump_primary_metadata())
                self.flfile.write(po.xml_dump_filelists_metadata())
                self.otherfile.write(po.xml_dump_other_metadata(
                    clog_limit=self.conf.changelog_limit))

        if pkgfiles:
            # divide that list by the number of workers and fork off that many
            # workers to tmpdirs
            # waitfor the workers to finish and as each one comes in
            # open the files they created and write them out to our metadata
            # add up the total pkg counts and return that value
            self._worker_tmp_path = tempfile.mkdtemp() # setting this in the base object so we can clean it up later
            if self.conf.workers < 1:
                self.conf.workers = min(num_cpus_online(), len(pkgfiles))
            pkgfiles.sort()
            worker_chunks = split_list_into_equal_chunks(pkgfiles, self.conf.workers)
            worker_cmd_dict = {}
            worker_jobs = {}
            base_worker_cmdline = [self.conf.worker_cmd, 
                    '--pkgoptions=_reldir=%s' % reldir,
                    '--pkgoptions=_collapse_libc_requires=%s' % self.conf.collapse_glibc_requires, 
                    '--pkgoptions=_cachedir=%s' % self.conf.cachedir,
                    '--pkgoptions=_baseurl=%s' % self.conf.baseurl,
                    '--globalopts=clog_limit=%s' % self.conf.changelog_limit,
                    '--globalopts=sumtype=%s' % self.conf.sumtype, ]
            
            if self.conf.quiet:
                base_worker_cmdline.append('--quiet')
            
            if self.conf.verbose:
                base_worker_cmdline.append('--verbose')
                
            for worker_num in range(self.conf.workers):
                pkl = self._worker_tmp_path + '/pkglist-%s' % worker_num
                f = open(pkl, 'w') 
                f.write('\n'.join(worker_chunks[worker_num]))
                f.close()
                
                workercmdline = []
                workercmdline.extend(base_worker_cmdline)
                workercmdline.append('--pkglist=%s/pkglist-%s' % (self._worker_tmp_path, worker_num))
                worker_cmd_dict[worker_num] = workercmdline
            
                

            for (num, cmdline) in worker_cmd_dict.items():
                if not self.conf.quiet:
                    self.callback.log("Spawning worker %s with %s pkgs" % (num, 
                                                      len(worker_chunks[num])))
                job = subprocess.Popen(cmdline, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                worker_jobs[num] = job
            
            files = self.primaryfile, self.flfile, self.otherfile
            def log_messages(num):
                job = worker_jobs[num]
                while True:
                    # check stdout and stderr
                    for stream in select((job.stdout, job.stderr), (), ())[0]:
                        line = stream.readline()
                        if line: break
                    else:
                        return # EOF, EOF
                    if stream is job.stdout:
                        if line.startswith('*** '):
                            # get data, save to local files
                            for out, size in zip(files, line[4:].split()):
                                out.write(stream.read(int(size)))
                            return
                        self.callback.log('Worker %s: %s' % (num, line.rstrip()))
                    else:
                        self.callback.errorlog('Worker %s: %s' % (num, line.rstrip()))

            for i, pkg in enumerate(pkgfiles):
                # insert cached packages
                save_keptpkgs(pkg)

                # save output to local files
                log_messages(i % self.conf.workers)

            for (num, job) in worker_jobs.items():
                # process remaining messages on stderr
                log_messages(num)

                if job.wait() != 0:
                    msg = "Worker exited with non-zero value: %s. Fatal." % job.returncode
                    self.callback.errorlog(msg)
                    raise MDError, msg
                    
            if not self.conf.quiet:
                self.callback.log("Workers Finished")
                    
            for pkgfile in pkgfiles:
                if self.conf.deltas:
                    try:
                        po = self.read_in_package(pkgfile, pkgpath=pkgpath, reldir=reldir)
                        self._do_delta_rpm_package(po)
                    except MDError, e:
                        errorprint(e)
                        continue
                self.read_pkgs.append(pkgfile)

        save_keptpkgs(None) # append anything left
        return self.current_pkg


    def closeMetadataDocs(self):
        # save them up to the tmp locations:
        if not self.conf.quiet:
            self.callback.log(_('Saving Primary metadata'))
        if self.conf.database_only:
            self.md_sqlite.pri_cx.close()
        else:
            self.primaryfile.write('\n</metadata>')
            self.primaryfile.close()

        if not self.conf.quiet:
            self.callback.log(_('Saving file lists metadata'))
        if self.conf.database_only:
            self.md_sqlite.file_cx.close()
        else:
            self.flfile.write('\n</filelists>')
            self.flfile.close()

        if not self.conf.quiet:
            self.callback.log(_('Saving other metadata'))
        if self.conf.database_only:
            self.md_sqlite.other_cx.close()
        else:
            self.otherfile.write('\n</otherdata>')
            self.otherfile.close()

        if self.conf.deltas:
            deltam_st = time.time()
            if not self.conf.quiet:
                self.callback.log(_('Saving delta metadata'))
            self.deltafile.write(self.generate_delta_xml())
            self.deltafile.write('\n</prestodelta>')
            self.deltafile.close()
            if self.conf.profile:
                self.callback.log('deltam time: %0.3f' % (time.time() - deltam_st))

    def _do_delta_rpm_package(self, pkg):
        """makes the drpms, if possible, for this package object.
           returns the presto/delta xml metadata as a string
        """
        drpm_pkg_time = time.time()
        # duck and cover if the pkg.size is > whatever
        if int(pkg.size) > self.conf.max_delta_rpm_size:
            if not self.conf.quiet:
                self.callback.log("Skipping %s package " \
                                    "that is > max_delta_rpm_size"  % pkg)
            return

        # generate a list of all the potential 'old rpms'
        opd = self._get_old_package_dict()
        # for each of our old_package_paths -
        # make a drpm from the newest of that pkg
        # get list of potential candidates which are likely to match
        for d in self.conf.oldpackage_paths:
            pot_cand = []
            if d not in opd:
                continue
            for fn in opd[d]:
                if os.path.basename(fn).startswith(pkg.name):
                    pot_cand.append(fn)

            candidates = []
            for fn in pot_cand:
                try:
                    thispo = yumbased.CreateRepoPackage(self.ts, fn,
                                                     sumtype=self.conf.sumtype)
                except Errors.MiscError, e:
                    continue
                if (thispo.name, thispo.arch) != (pkg.name, pkg.arch):
                    # not the same, doesn't matter
                    continue
                if thispo == pkg: #exactly the same, doesn't matter
                    continue
                if thispo.EVR >= pkg.EVR: # greater or equal, doesn't matter
                    continue
                candidates.append(thispo)
                candidates.sort()
                candidates.reverse()

            for delta_p in candidates[0:self.conf.num_deltas]:
                #make drpm of pkg and delta_p
                dt_st = time.time()
                drpmfn = deltarpms.create_drpm(delta_p, pkg, self.conf.deltadir)
                if not self.conf.quiet or self.conf.profile:
                    self.callback.log('created drpm from %s to %s: %s in %0.3f' % (
                        delta_p, pkg, drpmfn, (time.time() - dt_st)))
        if self.conf.profile:
            self.callback.log('total drpm time for %s: %0.3f' % (pkg,
                                                 (time.time() - drpm_pkg_time)))

    def _get_old_package_dict(self):
        if hasattr(self, '_old_package_dict'):
            return self._old_package_dict

        self._old_package_dict = {}
        for d in self.conf.oldpackage_paths:
            for f in self.getFileList(d, '.rpm'):
                fp = d + '/' + f
                fpstat = os.stat(fp)
                if int(fpstat[stat.ST_SIZE]) > self.conf.max_delta_rpm_size:
                    self.callback.log("Skipping %s package " \
                                      "that is > max_delta_rpm_size"  % f)
                    continue
                if not self._old_package_dict.has_key(d):
                    self._old_package_dict[d] = []
                self._old_package_dict[d].append(d + '/' + f)

        return self._old_package_dict

    def generate_delta_xml(self):
        """take the delta rpm output dir, process all the drpm files
           produce the text output for the presto/delta xml metadata"""
        # go through the drpm dir
        # for each file -store the drpm info in a dict based on its target. Just
        # appending the output. for each of the keys in the dict, return
        # the tag for the target + each of the drpm infos + closure for the target
        # tag
        targets = {}
        results = []
        for drpm_fn in self.getFileList(self.conf.deltadir, '.drpm'):
            drpm_rel_fn = os.path.normpath(self.conf.delta_relative +
                                           '/' + drpm_fn) # this is annoying
            drpm_po = yumbased.CreateRepoPackage(self.ts,
                 self.conf.deltadir + '/' + drpm_fn, sumtype=self.conf.sumtype)

            drpm = deltarpms.DeltaRPMPackage(drpm_po, self.conf.outputdir,
                                             drpm_rel_fn)
            if not targets.has_key(drpm_po.pkgtup):
                targets[drpm_po.pkgtup] = []
            targets[drpm_po.pkgtup].append(drpm.xml_dump_metadata())

        for (n, a, e, v, r) in targets.keys():
            results.append("""  <newpackage name="%s" epoch="%s" version="%s" release="%s" arch="%s">\n""" % (
                    n, e, v, r, a))
            results.extend(targets[(n,a,e,v,r)])
#            for src in targets[(n, a, e, v, r)]:
#                results.append(src)

            results.append("   </newpackage>\n")

        return ' '.join(results)

    def _createRepoDataObject(self, mdfile, mdtype, compress=True, 
                              compress_type=None, attribs={}):
        """return random metadata as RepoData object to be  added to RepoMD
           mdfile = complete path to file
           mdtype = the metadata type to use
           compress = compress the file before including it
        """
        # copy the file over here
        sfile = os.path.basename(mdfile)
        fo = open(mdfile, 'r')
        outdir = os.path.join(self.conf.outputdir, self.conf.tempdir)
        if not compress_type:
            compress_type = self.conf.compress_type
        if compress:
            sfile = '%s.%s' % (sfile, compress_type)
            outfn = os.path.join(outdir, sfile)
            output = compressOpen(outfn, mode='wb', compress_type=compress_type)
                
        else:
            outfn  = os.path.join(outdir, sfile)
            output = open(outfn, 'w')

        output.write(fo.read())
        output.close()
        fo.seek(0)
        open_csum = misc.checksum(self.conf.sumtype, fo)
        fo.close()


        if self.conf.unique_md_filenames:
            (csum, outfn) = checksum_and_rename(outfn, self.conf.sumtype)
            sfile = os.path.basename(outfn)
        else:
            if compress:
                csum = misc.checksum(self.conf.sumtype, outfn)
            else:
                csum = open_csum

        thisdata = RepoData()
        thisdata.type = mdtype
        thisdata.location = (self.conf.baseurl, os.path.join(self.conf.finaldir, sfile))
        thisdata.checksum = (self.conf.sumtype, csum)
        if compress:
            thisdata.openchecksum  = (self.conf.sumtype, open_csum)
        
        thisdata.size = str(os.stat(outfn).st_size)
        thisdata.timestamp = str(int(os.stat(outfn).st_mtime))
        for (k, v) in attribs.items():
            setattr(thisdata, k, str(v))
        
        return thisdata
        

    def doRepoMetadata(self):
        """wrapper to generate the repomd.xml file that stores the info
           on the other files"""
        
        repomd = RepoMD('repoid')
        repomd.revision = self.conf.revision

        repopath = os.path.join(self.conf.outputdir, self.conf.tempdir)
        repofilepath = os.path.join(repopath, self.conf.repomdfile)

        if self.conf.content_tags:
            repomd.tags['content'] = self.conf.content_tags
        if self.conf.distro_tags:
            repomd.tags['distro'] = self.conf.distro_tags
            # NOTE - test out the cpeid silliness here
        if self.conf.repo_tags:
            repomd.tags['repo'] = self.conf.repo_tags
            

        sumtype = self.conf.sumtype
        workfiles = [(self.conf.otherfile, 'other',),
                     (self.conf.filelistsfile, 'filelists'),
                     (self.conf.primaryfile, 'primary')]

        if self.conf.deltas:
            workfiles.append((self.conf.deltafile, 'prestodelta'))
        
        if self.conf.database:
            if not self.conf.quiet: self.callback.log('Generating sqlite DBs')
            try:
                dbversion = str(sqlitecachec.DBVERSION)
            except AttributeError:
                dbversion = '9'
            #FIXME - in theory some sort of try/except  here
            rp = sqlitecachec.RepodataParserSqlite(repopath, repomd.repoid, None)

        for (rpm_file, ftype) in workfiles:
            # when we fix y-m-p and non-gzipped xml files - then we can make this just add
            # self.conf.compress_type
            if ftype in ('other', 'filelists', 'primary'):
                rpm_file = rpm_file + '.' + 'gz'
            elif rpm_file.find('.') != -1 and rpm_file.split('.')[-1] not in _available_compression:
                rpm_file = rpm_file + '.' + self.conf.compress_type
            complete_path = os.path.join(repopath, rpm_file)
            zfo = compressOpen(complete_path)
            # This is misc.checksum() done locally so we can get the size too.
            data = misc.Checksums([sumtype])
            while data.read(zfo, 2**16):
                pass
            uncsum = data.hexdigest(sumtype)
            unsize = len(data)
            zfo.close()
            csum = misc.checksum(sumtype, complete_path)
            timestamp = os.stat(complete_path)[8]

            db_csums = {}
            db_compressed_sums = {}

            if self.conf.database:
                if ftype in ['primary', 'filelists', 'other']:
                    if self.conf.verbose:
                        self.callback.log("Starting %s db creation: %s" % (ftype,
                                                                  time.ctime()))

                if ftype == 'primary':
                    #FIXME - in theory some sort of try/except  here
                    # TypeError appears to be raised, sometimes :(
                    rp.getPrimary(complete_path, csum)

                elif ftype == 'filelists':
                    #FIXME and here
                    rp.getFilelists(complete_path, csum)

                elif ftype == 'other':
                    #FIXME and here
                    rp.getOtherdata(complete_path, csum)

                if ftype in ['primary', 'filelists', 'other']:
                    tmp_result_name = '%s.xml.gz.sqlite' % ftype
                    tmp_result_path = os.path.join(repopath, tmp_result_name)
                    good_name = '%s.sqlite' % ftype
                    resultpath = os.path.join(repopath, good_name)

                    # compat compression for rhel5 compatibility from fedora :(
                    compress_type = self.conf.compress_type
                    if self.compat_compress:
                        compress_type = 'bz2'
                        
                    # rename from silly name to not silly name
                    os.rename(tmp_result_path, resultpath)
                    compressed_name = '%s.%s' % (good_name, compress_type)
                    result_compressed = os.path.join(repopath, compressed_name)
                    db_csums[ftype] = misc.checksum(sumtype, resultpath)

                    # compress the files

                    compressFile(resultpath, result_compressed, compress_type)
                    # csum the compressed file
                    db_compressed_sums[ftype] = misc.checksum(sumtype,
                                                             result_compressed)
                    # timestamp+size the uncompressed file
                    un_stat = os.stat(resultpath)
                    # remove the uncompressed file
                    os.unlink(resultpath)

                    if self.conf.unique_md_filenames:
                        csum_compressed_name = '%s-%s.%s' % (
                                           db_compressed_sums[ftype], good_name, compress_type)
                        csum_result_compressed =  os.path.join(repopath,
                                                           csum_compressed_name)
                        os.rename(result_compressed, csum_result_compressed)
                        result_compressed = csum_result_compressed
                        compressed_name = csum_compressed_name

                    # timestamp+size the compressed file
                    db_stat = os.stat(result_compressed)

                    # add this data as a section to the repomdxml
                    db_data_type = '%s_db' % ftype
                    data = RepoData()
                    data.type = db_data_type
                    data.location = (self.conf.baseurl, 
                              os.path.join(self.conf.finaldir, compressed_name))
                    data.checksum = (sumtype, db_compressed_sums[ftype])
                    data.timestamp = str(int(db_stat.st_mtime))
                    data.size = str(db_stat.st_size)
                    data.opensize = str(un_stat.st_size)
                    data.openchecksum = (sumtype, db_csums[ftype])
                    data.dbversion = dbversion
                    if self.conf.verbose:
                        self.callback.log("Ending %s db creation: %s" % (ftype,
                                                                  time.ctime()))
                    repomd.repoData[data.type] = data
                    
            data = RepoData()
            data.type = ftype
            data.checksum = (sumtype, csum)
            data.timestamp = str(timestamp)
            data.size = str(os.stat(os.path.join(repopath, rpm_file)).st_size)
            data.opensize = str(unsize)
            data.openchecksum = (sumtype, uncsum)

            if self.conf.unique_md_filenames:
                if ftype in ('primary', 'filelists', 'other'):
                    compress = 'gz'
                else:
                    compress = self.conf.compress_type
                
                main_name = '.'.join(rpm_file.split('.')[:-1])
                res_file = '%s-%s.%s' % (csum, main_name, compress)
                orig_file = os.path.join(repopath, rpm_file)
                dest_file = os.path.join(repopath, res_file)
                os.rename(orig_file, dest_file)
            else:
                res_file = rpm_file
            rpm_file = res_file
            href = os.path.join(self.conf.finaldir, rpm_file)

            data.location = (self.conf.baseurl, href)
            repomd.repoData[data.type] = data

        if not self.conf.quiet and self.conf.database:
            self.callback.log('Sqlite DBs complete')


        if self.conf.groupfile is not None:
            mdcontent = self._createRepoDataObject(self.conf.groupfile, 'group_gz')
            repomd.repoData[mdcontent.type] = mdcontent
            
            mdcontent = self._createRepoDataObject(self.conf.groupfile, 'group',
                              compress=False)
            repomd.repoData[mdcontent.type] = mdcontent
            

        if self.conf.additional_metadata:
            for md_type, md_file in self.conf.additional_metadata.items():
                mdcontent = self._createRepoDataObject(md_file, md_type)
                repomd.repoData[mdcontent.type] = mdcontent
                

        # FIXME - disabled until we decide how best to use this
        #if self.rpmlib_reqs:
        #    rpmlib = reporoot.newChild(rpmns, 'lib', None)
        #    for r in self.rpmlib_reqs.keys():
        #        req  = rpmlib.newChild(rpmns, 'requires', r)


        # save it down
        try:
            fo = open(repofilepath, 'w')
            fo.write(repomd.dump_xml())
            fo.close()
        except (IOError, OSError, TypeError), e:
            self.callback.errorlog(
                  _('Error saving temp file for repomd.xml: %s') % repofilepath)
            self.callback.errorlog('Error was: %s') % str(e)
            fo.close()
            raise MDError, 'Could not save temp file: %s' % repofilepath
            

    def doFinalMove(self):
        """move the just-created repodata from .repodata to repodata
           also make sure to preserve any files we didn't mess with in the
           metadata dir"""

        output_final_dir = os.path.join(self.conf.outputdir, self.conf.finaldir)
        output_old_dir = os.path.join(self.conf.outputdir, self.conf.olddir)

        if os.path.exists(output_final_dir):
            try:
                os.rename(output_final_dir, output_old_dir)
            except:
                raise MDError, _('Error moving final %s to old dir %s' % (
                                 output_final_dir, output_old_dir))

        output_temp_dir = os.path.join(self.conf.outputdir, self.conf.tempdir)

        try:
            os.rename(output_temp_dir, output_final_dir)
        except:
            # put the old stuff back
            os.rename(output_old_dir, output_final_dir)
            raise MDError, _('Error moving final metadata into place')

        for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile',
                 'groupfile']:
            if getattr(self.conf, f):
                fn = os.path.basename(getattr(self.conf, f))
            else:
                continue
            oldfile = os.path.join(output_old_dir, fn)

            if os.path.exists(oldfile):
                try:
                    os.remove(oldfile)
                except OSError, e:
                    raise MDError, _(
                    'Could not remove old metadata file: %s: %s') % (oldfile, e)

        old_to_remove = []
        old_pr = []
        old_fl = []
        old_ot = []
        old_pr_db = []
        old_fl_db = []
        old_ot_db = []
        for f in os.listdir(output_old_dir):
            oldfile = os.path.join(output_old_dir, f)
            finalfile = os.path.join(output_final_dir, f)

            for (end,lst) in (('-primary.sqlite', old_pr_db), ('-primary.xml', old_pr),
                           ('-filelists.sqlite', old_fl_db), ('-filelists.xml', old_fl),
                           ('-other.sqlite', old_ot_db), ('-other.xml', old_ot)):
                fn = '.'.join(f.split('.')[:-1])
                if fn.endswith(end):
                    lst.append(oldfile)
                    break

        # make a list of the old metadata files we don't want to remove.
        for lst in (old_pr, old_fl, old_ot, old_pr_db, old_fl_db, old_ot_db):
            sortlst = sorted(lst, key=lambda x: os.path.getmtime(x),
                             reverse=True)
            for thisf in sortlst[self.conf.retain_old_md:]:
                old_to_remove.append(thisf)

        for f in os.listdir(output_old_dir):
            oldfile = os.path.join(output_old_dir, f)
            finalfile = os.path.join(output_final_dir, f)
            fn = '.'.join(f.split('.')[:-1])
            if fn in ('filelists.sqlite', 'other.sqlite',
                     'primary.sqlite') or oldfile in old_to_remove:
                try:
                    os.remove(oldfile)
                except (OSError, IOError), e:
                    raise MDError, _(
                    'Could not remove old metadata file: %s: %s') % (oldfile, e)
                continue

            if os.path.exists(finalfile):
                # Hmph?  Just leave it alone, then.
                try:
                    if os.path.isdir(oldfile):
                        shutil.rmtree(oldfile)
                    else:
                        os.remove(oldfile)
                except OSError, e:
                    raise MDError, _(
                    'Could not remove old metadata file: %s: %s') % (oldfile, e)
            else:
                try:
                    os.rename(oldfile, finalfile)
                except OSError, e:
                    msg = _('Could not restore old non-metadata file: %s -> %s') % (oldfile, finalfile)
                    msg += _('Error was %s') % e
                    raise MDError, msg

        self._cleanup_tmp_repodata_dir()
        self._cleanup_update_tmp_dir()        
        self._write_out_read_pkgs_list()


    def _cleanup_update_tmp_dir(self):
        if not self.conf.update:
            return
        
        shutil.rmtree(self.oldData._repo.basecachedir, ignore_errors=True)
        shutil.rmtree(self.oldData._repo.base_persistdir, ignore_errors=True)
        
    def _write_out_read_pkgs_list(self):
        # write out the read_pkgs_list file with self.read_pkgs
        if self.conf.read_pkgs_list:
            try:
                fo = open(self.conf.read_pkgs_list, 'w')
                fo.write('\n'.join(self.read_pkgs))
                fo.flush()
                fo.close()
            except (OSError, IOError), e:
                self.errorlog(_('Could not write out readpkgs list: %s')
                              % self.conf.read_pkgs_list)
                self.errorlog(_('Error was %s') % e)

    def _cleanup_tmp_repodata_dir(self):
        output_old_dir = os.path.join(self.conf.outputdir, self.conf.olddir)
        output_temp_dir = os.path.join(self.conf.outputdir, self.conf.tempdir)
        for dirbase in (self.conf.olddir, self.conf.tempdir):
            dirpath = os.path.join(self.conf.outputdir, dirbase)
            if os.path.exists(dirpath):
                try:
                    os.rmdir(dirpath)
                except OSError, e:
                    self.errorlog(_('Could not remove  temp metadata dir: %s')
                                  % dirbase)
                    self.errorlog(_('Error was %s') % e)
                    self.errorlog(_('Please clean up this directory manually.'))
        # our worker tmp path
        if hasattr(self, '_worker_tmp_path') and os.path.exists(self._worker_tmp_path):
            shutil.rmtree(self._worker_tmp_path, ignore_errors=True)
        
    def setup_sqlite_dbs(self, initdb=True):
        """sets up the sqlite dbs w/table schemas and db_infos"""
        destdir = os.path.join(self.conf.outputdir, self.conf.tempdir)
        try:
            self.md_sqlite = MetaDataSqlite(destdir)
        except sqlite.OperationalError, e:
            raise MDError, _('Cannot create sqlite databases: %s.\n'\
                'Maybe you need to clean up a .repodata dir?') % e



class SplitMetaDataGenerator(MetaDataGenerator):
    """takes a series of dirs and creates repodata for all of them
       most commonly used with -u media:// - if no outputdir is specified
       it will create the repodata in the first dir in the list of dirs
       """
    def __init__(self, config_obj=None, callback=None):
        MetaDataGenerator.__init__(self, config_obj=config_obj, callback=None)

    def _getFragmentUrl(self, url, fragment):
        import urlparse
        urlparse.uses_fragment.append('media')
        if not url:
            return url
        (scheme, netloc, path, query, fragid) = urlparse.urlsplit(url)
        return urlparse.urlunsplit((scheme, netloc, path, query, str(fragment)))

    def doPkgMetadata(self):
        """all the heavy lifting for the package metadata"""
        if len(self.conf.directories) == 1:
            MetaDataGenerator.doPkgMetadata(self)
            return

        if self.conf.update:
            self._setup_old_metadata_lookup()

        filematrix = {}
        for mydir in self.conf.directories:
            if os.path.isabs(mydir):
                thisdir = mydir
            else:
                if mydir.startswith('../'):
                    thisdir = os.path.realpath(mydir)
                else:
                    thisdir = os.path.join(self.conf.basedir, mydir)

            filematrix[mydir] = self.getFileList(thisdir, '.rpm')

            #  pkglist is a bit different for split media, as we have to know
            # which dir. it belongs to. So we walk the dir. and then filter.
            # We could be faster by not walking the dir. ... but meh.
            if self.conf.pkglist:
                pkglist = set(self.conf.pkglist)
                pkgs = []
                for fname in filematrix[mydir]:
                    if fname not in pkglist:
                        continue
                    pkgs.append(fname)
                filematrix[mydir] = pkgs

            self.trimRpms(filematrix[mydir])
            self.pkgcount += len(filematrix[mydir])

        mediano = 1
        self.current_pkg = 0
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
        try:
            self.openMetadataDocs()
            for mydir in self.conf.directories:
                self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
                self.writeMetadataDocs(filematrix[mydir], mydir)
                mediano += 1
            self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, 1)
            self.closeMetadataDocs()
        except (IOError, OSError), e:
            raise MDError, _('Cannot access/write repodata files: %s') % e



class MetaDataSqlite(object):
    def __init__(self, destdir):
        self.pri_sqlite_file = os.path.join(destdir, 'primary.sqlite')
        self.pri_cx = sqlite.Connection(self.pri_sqlite_file)
        self.file_sqlite_file = os.path.join(destdir, 'filelists.sqlite')
        self.file_cx = sqlite.Connection(self.file_sqlite_file)
        self.other_sqlite_file = os.path.join(destdir, 'other.sqlite')
        self.other_cx = sqlite.Connection(self.other_sqlite_file)
        self.primary_cursor = self.pri_cx.cursor()

        self.filelists_cursor = self.file_cx.cursor()

        self.other_cursor = self.other_cx.cursor()

        self.create_primary_db()
        self.create_filelists_db()
        self.create_other_db()

    def create_primary_db(self):
        # make the tables
        schema = [
        """PRAGMA synchronous="OFF";""",
        """pragma locking_mode="EXCLUSIVE";""",
        """CREATE TABLE conflicts (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER );""",
        """CREATE TABLE db_info (dbversion INTEGER, checksum TEXT);""",
        """CREATE TABLE files (  name TEXT,  type TEXT,  pkgKey INTEGER);""",
        """CREATE TABLE obsoletes (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER );""",
        """CREATE TABLE packages (  pkgKey INTEGER PRIMARY KEY,  pkgId TEXT,  name TEXT,  arch TEXT,  version TEXT,  epoch TEXT,  release TEXT,  summary TEXT,  description TEXT,  url TEXT,  time_file INTEGER,  time_build INTEGER,  rpm_license TEXT,  rpm_vendor TEXT,  rpm_group TEXT,  rpm_buildhost TEXT,  rpm_sourcerpm TEXT,  rpm_header_start INTEGER,  rpm_header_end INTEGER,  rpm_packager TEXT,  size_package INTEGER,  size_installed INTEGER,  size_archive INTEGER,  location_href TEXT,  location_base TEXT,  checksum_type TEXT);""",
        """CREATE TABLE provides (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER );""",
        """CREATE TABLE requires (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER , pre BOOL DEFAULT FALSE);""",
        """CREATE INDEX filenames ON files (name);""",
        """CREATE INDEX packageId ON packages (pkgId);""",
        """CREATE INDEX packagename ON packages (name);""",
        """CREATE INDEX pkgconflicts on conflicts (pkgKey);""",
        """CREATE INDEX pkgobsoletes on obsoletes (pkgKey);""",
        """CREATE INDEX pkgprovides on provides (pkgKey);""",
        """CREATE INDEX pkgrequires on requires (pkgKey);""",
        """CREATE INDEX providesname ON provides (name);""",
        """CREATE INDEX requiresname ON requires (name);""",
        """CREATE TRIGGER removals AFTER DELETE ON packages
             BEGIN
             DELETE FROM files WHERE pkgKey = old.pkgKey;
             DELETE FROM requires WHERE pkgKey = old.pkgKey;
             DELETE FROM provides WHERE pkgKey = old.pkgKey;
             DELETE FROM conflicts WHERE pkgKey = old.pkgKey;
             DELETE FROM obsoletes WHERE pkgKey = old.pkgKey;
             END;""",
         """INSERT into db_info values (%s, 'direct_create');""" % sqlitecachec.DBVERSION,
             ]

        for cmd in schema:
            executeSQL(self.primary_cursor, cmd)

    def create_filelists_db(self):
        schema = [
            """PRAGMA synchronous="OFF";""",
            """pragma locking_mode="EXCLUSIVE";""",
            """CREATE TABLE db_info (dbversion INTEGER, checksum TEXT);""",
            """CREATE TABLE filelist (  pkgKey INTEGER,  dirname TEXT,  filenames TEXT,  filetypes TEXT);""",
            """CREATE TABLE packages (  pkgKey INTEGER PRIMARY KEY,  pkgId TEXT);""",
            """CREATE INDEX dirnames ON filelist (dirname);""",
            """CREATE INDEX keyfile ON filelist (pkgKey);""",
            """CREATE INDEX pkgId ON packages (pkgId);""",
            """CREATE TRIGGER remove_filelist AFTER DELETE ON packages
                   BEGIN
                   DELETE FROM filelist WHERE pkgKey = old.pkgKey;
                   END;""",
         """INSERT into db_info values (%s, 'direct_create');""" % sqlitecachec.DBVERSION,
            ]
        for cmd in schema:
            executeSQL(self.filelists_cursor, cmd)

    def create_other_db(self):
        schema = [
            """PRAGMA synchronous="OFF";""",
            """pragma locking_mode="EXCLUSIVE";""",
            """CREATE TABLE changelog (  pkgKey INTEGER,  author TEXT,  date INTEGER,  changelog TEXT);""",
            """CREATE TABLE db_info (dbversion INTEGER, checksum TEXT);""",
            """CREATE TABLE packages (  pkgKey INTEGER PRIMARY KEY,  pkgId TEXT);""",
            """CREATE INDEX keychange ON changelog (pkgKey);""",
            """CREATE INDEX pkgId ON packages (pkgId);""",
            """CREATE TRIGGER remove_changelogs AFTER DELETE ON packages
                 BEGIN
                 DELETE FROM changelog WHERE pkgKey = old.pkgKey;
                 END;""",
         """INSERT into db_info values (%s, 'direct_create');""" % sqlitecachec.DBVERSION,
            ]

        for cmd in schema:
            executeSQL(self.other_cursor, cmd)
