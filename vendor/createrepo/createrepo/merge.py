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
# Copyright 2008  Red Hat, Inc - written by seth vidal skvidal at fedoraproject.org

# merge repos from arbitrary repo urls

import os
import shutil
import yum
import yum.Errors
from yum.misc import unique, getCacheDir
import yum.update_md
import rpmUtils.arch
import operator
from utils import MDError
import createrepo
import tempfile

# take repo paths from cli
# produce new repo metadata from merging the two together.

#TODO:
# excludes?


class RepoMergeBase:
    def __init__(self, repolist=[], yumbase=None, mdconf=None, mdbase_class=None ):
        self.repolist = repolist
        self.outputdir = '%s/merged_repo' % os.getcwd()
        self.exclude_tuples = []
        self.sort_func = self._sort_func # callback function to magically sort pkgs
        if not mdconf:
            self.mdconf = createrepo.MetaDataConfig()
        else:
            self.mdconf = mdconf
        if not mdbase_class:
            self.mdbase_class = createrepo.MetaDataGenerator
        else:
            self.mdbase_class = mdbase_class
        if not yumbase:
            self.yumbase = yum.YumBase()
        else:
            self.yumbase = yumbase
        self.yumbase.conf.cachedir = getCacheDir()
        self.yumbase.conf.cache = 0
        # default to all arches
        self.archlist = unique(rpmUtils.arch.arches.keys() + rpmUtils.arch.arches.values())
        self.groups = True
        self.updateinfo = True

    def _sort_func(self, repos):
        """Default sort func for repomerge. Takes a list of repository objects
           any package which is not to be included in the merged repo should be
           delPackage()'d"""
        # sort the repos by _merge_rank
        # - lowest number is the highest rank (1st place, 2ndplace, etc)
        repos.sort(key=operator.attrgetter('_merge_rank'))

        for repo in repos:
            for pkg in repo.sack:
                others = self.yumbase.pkgSack.searchNevra(pkg.name, pkg.epoch, pkg.version, pkg.release, pkg.arch)
                if len(others) > 1:
                    for thatpkg in others:
                        if pkg.repoid == thatpkg.repoid: continue
                        if pkg.repo._merge_rank < thatpkg.repo._merge_rank:
                            thatpkg.repo.sack.delPackage(thatpkg)

    def merge_repos(self):
        self.yumbase.repos.disableRepo('*')
        # add our repos and give them a merge rank in the order they appear in
        # in the repolist
        count = 0
        for r in self.repolist:
            if ':' not in r:
                r = os.path.abspath(r)
                r = 'file://' + r # just fix the file repos, this is silly.
            count +=1
            rid = 'repo%s' % count
            n = self.yumbase.add_enable_repo(rid, baseurls=[r],
                                             metadata_expire=0,
                                             timestamp_check=False)
            n._merge_rank = count

        #setup our sacks
        try:
            self.yumbase._getSacks(archlist=self.archlist)
        except yum.Errors.RepoError, e:
            raise MDError, "Could not setup merge repo pkgsack: %s" % e

        myrepos = self.yumbase.repos.listEnabled()

        self.sort_func(myrepos)


    def write_metadata(self, outputdir=None):
        mytempdir = tempfile.mkdtemp()
        if self.groups:
            try:
                comps_fn = mytempdir + '/groups.xml'
                compsfile = open(comps_fn, 'w')
                compsfile.write(self.yumbase.comps.xml())
                compsfile.close()
            except yum.Errors.GroupsError, e:
                # groups not being available shouldn't be a fatal error
                pass
            else:
                self.mdconf.groupfile=comps_fn

        if self.updateinfo:
            ui_fn = mytempdir + '/updateinfo.xml'
            uifile = open(ui_fn, 'w')
            umd = yum.update_md.UpdateMetadata()
            for repo in self.yumbase.repos.listEnabled():
                try: # attempt to grab the updateinfo.xml.gz from the repodata
                    umd.add(repo)
                except yum.Errors.RepoMDError:
                    continue
            umd.xml(fileobj=uifile)
            uifile.close()
            self.mdconf.additional_metadata['updateinfo'] = ui_fn


        self.mdconf.pkglist = self.yumbase.pkgSack
        self.mdconf.directory = self.outputdir
        if outputdir:
            self.mdconf.directory = outputdir
        # clean out what was there
        if os.path.exists(self.mdconf.directory + '/repodata'):
            shutil.rmtree(self.mdconf.directory + '/repodata')

        if not os.path.exists(self.mdconf.directory):
            os.makedirs(self.mdconf.directory)

        mdgen = self.mdbase_class(config_obj=self.mdconf)
        mdgen.doPkgMetadata()
        mdgen.doRepoMetadata()
        mdgen.doFinalMove()
