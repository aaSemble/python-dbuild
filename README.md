[![Travis-CI Status](https://travis-ci.org/aaSemble/python-dbuild.svg)](https://travis-ci.org/aaSemble/python-dbuild)
[![codecov.io](https://codecov.io/github/aaSemble/python-dbuild/coverage.svg?branch=master)](https://codecov.io/github/aaSemble/python-dbuild?branch=master)
#python-dbuild
python-dbuild is a tool that can be used to build Debian packages using docker
containers. This will improve the security compared with sbuild on package builds
by building the packages in separate containers.

This code is mostly a rewrite in python of
https://github.com/shadeslayer/dbuild, which is written in ruby.

# Prerequisites
 You need docker installed - usually installed on same machine where dbuild is
installed/used. But it support running containers in remote machines also - you
would need to configure docker to accept the requests from remote machines in
this case, and provide docker_url parameter when you call dbuild. Also the build
directory need to be present in docker host - either via a shared storage or the
build directory need to be copied over.

# Install
Use pip to install the package from git.

$ sudo pip install -e git+https://github.com/hkumarmk/python-dbuild.git#egg=dbuild

Note: You may use virtualenv to install this package if required

# Use dbuild

dbuild can be use as a command or as a python library. It accept a build-dir
which is the directory path where the source or source package is kept. Also it
accept various optional parameters with appropriate defaults.

The resultant package will be created/kept in the build_dir itself.

dbuild also support using any special apt repos which would have the build
dependency packages. dbuild expect following files under build_dir.

repos: This file contain all the repo source lists which need to be added on the
container before the build - this will need to be in the form which is suitable
for apt sources.list file.

keys: This file need to contain the repo keys for extra repos.

Alternatively you may keep it in different file name, and provide appropriate
parameters.

## dbuild as command

Once you install the package, the command "dbuild" is installed on the system.
You may just run dbuid or dbuild --help to get the help.

```
$ dbuild -h
usage: dbuild [-h] [--source-dir SOURCE_DIR] [--force-rm]
              [--docker-url DOCKER_URL] [--dist DIST] [--release RELEASE]
              [--extra-repos-file EXTRA_REPOS_FILE]
              [--extra-repo-keys-file EXTRA_REPO_KEYS_FILE] [--build-cache]
              build_dir

Build debian packages in docker container

positional arguments:
  build_dir             package build directory

optional arguments:
  -h, --help            show this help message and exit
  --source-dir SOURCE_DIR
                        subdirectory of build_dir where sources kept
  --force-rm            Remove the containers even if build failed
  --docker-url DOCKER_URL
                        Docker url, it can be unix socket or tcp url
  --dist DIST           Linux dist to use for container to build
  --release RELEASE     Linux release name
  --extra-repos-file EXTRA_REPOS_FILE
                        Relative file path from build-dir which contain apt
                        source specs which is suitable for apt sources.list
                        file.
  --extra-repo-keys-file EXTRA_REPO_KEYS_FILE
                        relative file path from build-dir which contain all
                        keys for any extra repos.
  --build-cache         Whether to use docker build cache or not
```

## dbuild as library

Once you install python-dbuild package, you can include dbuild in your
python code and call the dbuild methods from your application.

Build source package
```
import dbuild

dbuild.docker_build(build_dir='/tmp', build_type='source', source_dir='src',
                                                        build_owner='user1')
```

Build Binary package

You need to build source package in the build_dir (source package need to be
present in build_dir), before attempting binary build.

```
import dbuild
dbuild.docker_build(build_dir='/tmp', build_type='binary', build_owner='user1')
```
