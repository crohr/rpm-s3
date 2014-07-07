#!/usr/bin/python -tt

import sys
import yum
import createrepo
import os
import rpmUtils
import re
from optparse import OptionParser


# pass in dir to make tempdirs in
# make tempdir for this worker
# create 3 files in that tempdir
# return how many pkgs
# return on stderr where things went to hell

#TODO - take most of read_in_package from createrepo and duplicate it here
# so we can do downloads, etc.
# then replace callers of read_in_package with forked callers of this
# and reassemble at the end

def main(args):
    parser = OptionParser()
    parser.add_option('--tmpmdpath', default=None, 
                help="path where the outputs should be dumped for this worker")
    parser.add_option('--pkglist', default=None, 
                help="file to read the pkglist from in lieu of all of them on the cli")
    parser.add_option("--pkgoptions", default=[], action='append',
                help="pkgoptions in the format of key=value")
    parser.add_option("--quiet", default=False, action='store_true',
                help="only output errors and a total")
    parser.add_option("--verbose", default=False, action='store_true',
                help="output errors and a total")
    parser.add_option("--globalopts", default=[], action='append',
                help="general options in the format of key=value")

    
    opts, pkgs = parser.parse_args(args)
    external_data = {'_packagenumber': 1}
    globalopts = {}
    
    for strs in opts.pkgoptions:
        k,v = strs.split('=')
        if v in ['True', 'true', 'yes', '1', 1]:
            v = True
        elif v in ['False', 'false', 'no', '0', 0]:
            v = False
        elif v in ['None', 'none', '']:
            v = None
        external_data[k] = v

    for strs in opts.globalopts:
        k,v = strs.split('=')
        if v in ['True', 'true', 'yes', '1', 1]:
            v = True
        elif v in ['False', 'false', 'no', '0', 0]:
            v = False
        elif v in ['None', 'none', '']:
            v = None
        globalopts[k] = v

    # turn off buffering on stdout
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    
    reldir = external_data['_reldir']
    ts = rpmUtils.transaction.initReadOnlyTransaction()
    if opts.tmpmdpath:
        files = [open(opts.tmpmdpath + '/%s.xml' % i, 'w')
                 for i in ('primary', 'filelists', 'other')]
        def output(*xml):
            for fh, buf in zip(files, xml):
                fh.write(buf)
    else:
        def output(*xml):
            buf = ' '.join(str(len(i)) for i in xml)
            sys.stdout.write('*** %s\n' % buf)
            for buf in xml:
                sys.stdout.write(buf)

    if opts.pkglist:
        for line in open(opts.pkglist,'r').readlines():
            line = line.strip()
            if re.match('^\s*\#.*', line) or re.match('^\s*$', line):
                continue
            pkgs.append(line)

    clog_limit=globalopts.get('clog_limit', None)
    if clog_limit is not None:
         clog_limit = int(clog_limit)
    for pkgfile in pkgs:
        pkgpath = reldir + '/' + pkgfile
        if not os.path.exists(pkgpath):
            print >> sys.stderr, "File not found: %s" % pkgpath
            output()
            continue

        try:
            if not opts.quiet and opts.verbose:
                print "reading %s" % (pkgfile)

            pkg = createrepo.yumbased.CreateRepoPackage(ts, package=pkgpath, 
                                sumtype=globalopts.get('sumtype', None), 
                                external_data=external_data)
            output(pkg.xml_dump_primary_metadata(),
                   pkg.xml_dump_filelists_metadata(),
                   pkg.xml_dump_other_metadata(clog_limit=clog_limit))
        except yum.Errors.YumBaseError, e:
            print >> sys.stderr, "Error: %s" % e
            output()
            continue
        else:
            external_data['_packagenumber']+=1
        
if __name__ == "__main__":
    main(sys.argv[1:])
