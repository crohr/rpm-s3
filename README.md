This daemon script can be used to keep an s3-hosted yum repository updated
when new rpm packages are uploaded.  It is equivalent to using `createrepo`
and an `s3cmd sync`.  Only a temporary copy of the repo metadata is needed
locally, so there's no need to keep a full clone of the repository and all
it's packages.  This is also very useful if packages are uploaded by many
users or systems.  Having a single `repoupdate-daemon` will ensure all new
packages are added to the repository metadata, avoiding issues with
concurrent updates.

The upload of a new package to s3 should be handled by whatever client is
used to build the rpm, e.g. a CI system like Jenkins.  The daemon listens
for SNS notifications on an SQS queue which inform it of the path for these
new rpm files.  The daemon then downloads the repodata, updates, and uploads
again.

You can use the included `publish-packages` script to upload rpms to s3 and
notify the update daemon.

By default the daemon is configured to keep only the last two versions of
each package.

Install
-------

You can use the included spec file to build an rpm and then `yum localinstall`
it.

Configure
---------

Create an s3 bucket to host the yum repository.  Create an SNS topic and an SQS
queue that is subscribed to it.

Override default options:

    echo 'OPTIONS="$OPTIONS -b mybucket -q myqueue"' >/etc/sysconfig/repoupdate-daemon

The daemon uses standard boto configuation to access the AWS credentials: IAM
role, environment variables, or boto config file.

Run
---

    service repoupdate-daemon start

Test
----

    publish-packages --bucket mybucket --sns-topic mytopic *.rpm

---

Related Tools
-------------

https://github.com/seporaitis/yum-s3-iam
https://wiki.jenkins-ci.org/display/JENKINS/S3+Plugin
https://wiki.jenkins-ci.org/display/JENKINS/Amazon+SNS+Notifier
