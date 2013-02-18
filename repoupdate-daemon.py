#!/usr/bin/env python
"""Daemon for serialising metadata updates on an s3-hosted yum repository.

Listens on SQS for SNS messages that specify new packages published to s3.
After waiting a while and grouping any additional messages, this script will
update the yum repodata to include all the new packages.

Assuming you have an SQS queue subscribed to an SNS topic, you can upload
a package and notify this daemon by specifying the rpm filename in the SNS
message body (and optionally give the base repository path in the subject):
>>> bucket = boto.connect_s3().get_bucket('bucket')
>>> bucket.new_key('repo/path/mypackage.rpm').set_contents_from_string('...')
>>> boto.connect_sns().publish('TOPIC', 'mypackage.rpm', 'repo/path')
"""
import os
import time
import urlparse
import tempfile
import shutil
import optparse
import logging
import collections
import yum
import createrepo
import boto
import boto.sqs
import boto.sqs.message
from boto.sqs.jsonmessage import json


# Hack for creating s3 urls
urlparse.uses_relative.append('s3')
urlparse.uses_netloc.append('s3')


class LoggerCallback(object):
    def errorlog(self, message):
        logging.error(message)

    def log(self, message):
        message = message.strip()
        if message:
            logging.debug(message)


class S3Grabber(object):
    def __init__(self, baseurl):
        base = urlparse.urlsplit(baseurl)
        self.baseurl = baseurl
        self.basepath = base.path.lstrip('/')
        self.bucket = boto.connect_s3().get_bucket(base.netloc)

    def urlgrab(self, url, filename, **kwargs):
        if url.startswith(self.baseurl):
            url = url[len(self.baseurl):].lstrip('/')
        key = self.bucket.get_key(os.path.join(self.basepath, url))
        if not key:
            raise createrepo.grabber.URLGrabError(14, '%s not found' % url)
        logging.info('downloading: %s', key.name)
        key.get_contents_to_filename(filename)
        return filename

    def syncdir(self, dir, url):
        """Copy all files in dir to url, removing any existing keys."""
        base = os.path.join(self.basepath, url)
        existing_keys = list(self.bucket.list(base))
        new_keys = []
        for filename in sorted(os.listdir(dir)):
            key = self.bucket.new_key(os.path.join(base, filename))
            key.set_contents_from_filename(os.path.join(dir, filename))
            new_keys.append(key.name)
            logging.info('uploading: %s', key.name)
        for key in existing_keys:
            if key.name not in new_keys:
                key.delete()
                logging.info('removing: %s', key.name)


def update_repodata(repopath, rpmfiles, options):
    tmpdir = tempfile.mkdtemp()
    s3base = urlparse.urlunsplit(('s3', options.bucket, repopath, '', ''))
    s3grabber = S3Grabber(s3base)

    # Set up temporary repo that will fetch repodata from s3
    yumbase = yum.YumBase()
    yumbase.preconf.disabled_plugins = '*'
    yumbase.conf.cachedir = os.path.join(tmpdir, 'cache')
    yumbase.repos.disableRepo('*')
    repo = yumbase.add_enable_repo('s3')
    repo._grab = s3grabber
    # Ensure that missing base path doesn't cause trouble
    repo._sack = yum.sqlitesack.YumSqlitePackageSack(
        createrepo.readMetadata.CreaterepoPkgOld)

    # Create metadata generator
    mdconf = createrepo.MetaDataConfig()
    mdconf.directory = tmpdir
    mdgen = createrepo.MetaDataGenerator(mdconf, LoggerCallback())
    mdgen.tempdir = tmpdir
    mdgen._grabber = s3grabber

    # Combine existing package sack with new rpm file list
    new_packages = []
    for rpmfile in rpmfiles:
        newpkg = mdgen.read_in_package(os.path.join(s3base, rpmfile))
        newpkg._baseurl = ''   # don't leave s3 base urls in primary metadata
        older_pkgs = yumbase.pkgSack.searchNevra(name=newpkg.name)
        # Remove older versions of this package (or if it's the same version)
        for i, older in enumerate(reversed(older_pkgs), 1):
            if i > options.keep or older.pkgtup == newpkg.pkgtup:
                yumbase.pkgSack.delPackage(older)
                logging.info('ignoring: %s', older.ui_nevra)
        new_packages.append(newpkg)
    mdconf.pkglist = list(yumbase.pkgSack) + new_packages

    # Write out new metadata to tmpdir
    mdgen.doPkgMetadata()
    mdgen.doRepoMetadata()
    mdgen.doFinalMove()

    # Replace metadata on s3
    s3grabber.syncdir(os.path.join(tmpdir, 'repodata'), 'repodata')

    shutil.rmtree(tmpdir)


def main(options, args):
    loglevel = ('WARNING', 'INFO', 'DEBUG')[min(2, options.verbose)]
    logging.basicConfig(
        filename=options.logfile,
        level=logging.getLevelName(loglevel),
        format='%(asctime)s %(levelname)s %(message)s',
    )

    if args and not options.sqs_name:
        return update_repodata(options.repopath, args, options)

    conn = boto.sqs.connect_to_region(options.region)
    queue = conn.get_queue(options.sqs_name)
    queue.set_message_class(boto.sqs.message.RawMessage)
    messages = []
    delay_count = 0
    visibility_timeout = ((options.process_delay_count + 2) *
                          options.queue_check_interval)
    logging.debug('sqs visibility_timeout: %d', visibility_timeout)

    while True:
        new_messages = queue.get_messages(10, visibility_timeout)
        if new_messages:
            messages.extend(new_messages)
            # Immediately check for more messages
            continue
        if messages:
            if delay_count < options.process_delay_count:
                logging.debug('Delaying processing: %d < %d', delay_count,
                              options.process_delay_count)
                delay_count += 1
            else:
                pkgmap = collections.defaultdict(list)
                for message in messages:
                    body = json.loads(message.get_body())
                    repopath = str(body.get('Subject', options.repopath))
                    pkgmap[repopath].append(str(body['Message']))
                for repopath, rpmfiles in pkgmap.items():
                    logging.info('updating: %s: %r', repopath, rpmfiles)
                    try:
                        update_repodata(repopath, set(rpmfiles), options)
                    except:
                        # sqs messages will be deleted even on failure
                        logging.exception('update failed: %s', repopath)
                # Reset:
                for message in messages:
                    message.delete()
                messages = []
                delay_count = 0
        logging.debug('sleeping %ds...', options.queue_check_interval)
        try:
            time.sleep(options.queue_check_interval)
        except KeyboardInterrupt:
            break


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-b', '--bucket', default='packages.example.com')
    parser.add_option('-p', '--repopath', default='development/x86_64')
    parser.add_option('-r', '--region', default='us-east-1')
    parser.add_option('-q', '--sqs-name')
    parser.add_option('-k', '--keep', type='int', default=2)
    parser.add_option('-v', '--verbose', action='count', default=0)
    parser.add_option('-l', '--logfile')
    parser.add_option('-d', '--daemon', action='store_true')
    parser.add_option('-P', '--pidfile')
    parser.add_option('-U', '--user')
    parser.add_option('--queue-check-interval', type='int', default=60)
    parser.add_option('--process-delay-count', type='int', default=2)
    options, args = parser.parse_args()

    if not options.sqs_name and not args:
        parser.error("Must specify SQS queue name or rpm file args")
    if options.sqs_name and args:
        parser.error("Don't give file args when specifying an SQS queue")

    if options.daemon:
        import daemon
        daemon_args = {}
        if options.pidfile:
            from daemon.pidlockfile import PIDLockFile
            daemon_args['pidfile'] = PIDLockFile(options.pidfile)
        if options.user:
            import pwd
            user = pwd.getpwnam(options.user)
            daemon_args['uid'] = user.pw_uid
            daemon_args['gid'] = user.pw_gid
        with daemon.DaemonContext(**daemon_args):
            main(options, args)
    else:
        main(options, args)
