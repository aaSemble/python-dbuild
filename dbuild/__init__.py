#!/usr/bin/env python
import argparse
import codecs
import os
import shutil
import sys
from tempfile import mkdtemp

from docker import Client

from jinja2 import Environment, FileSystemLoader

import six

from dbuild import exceptions


def docker_client(url='unix://var/run/docker.sock'):
    """ return docker client """
    return Client(url)


def build_image(docker_client, path, tag, nocache=False):
    """ Build docker image"""
    for line in docker_client.build(path=path, rm=True, forcerm=True,
                                    tag=tag, decode=True, nocache=nocache):
        if 'stream' in line:
            yield line['stream']
        if 'error' in line:
            raise exceptions.DbuildDockerBuildFailedException(line['error'], line.get('errorDetails'))


def create_container(docker_client, image, name=None, command=None, env=None,
                     disable_network=False, shared_volumes=None, cwd=None):
    """ create docker containers """
    if shared_volumes:
        volumes = list(shared_volumes.values())
        binds = ['{}:{}'.format(k, v) for k, v in six.iteritems(shared_volumes)]
        host_config = docker_client.create_host_config(binds=binds)
    else:
        volumes = None
        host_config = None

    container = docker_client.create_container(
        image=image, name=name, command=command, environment=env,
        network_disabled=disable_network, volumes=volumes,
        working_dir=cwd, host_config=host_config)
    return container


def start_container(docker_client, container):
    """ Start docker container """
    response = docker_client.start(container=container.get('Id'))
    return response


def wait_container(docker_client, container):
    """ Wait  for the container to finish execution """
    rv = docker_client.wait(container=container)
    return rv


def container_logs(docker_client, container, include_timestamps=True):
    """ Get container stdout and stderr """
    for log in docker_client.logs(container=container, stream=True,
                                  timestamps=include_timestamps):
        yield log.strip()


def remove_container(docker_client, container, force=False):
    """ Remove docker container """
    return docker_client.remove_container(container=container, force=force)


def create_dockerfile(dist, release, docker_dir, proxy=""):
    """Create docker directory and populate it"""
    PATH = os.path.dirname(os.path.abspath(__file__))
    TMPL_ENV = Environment(
        autoescape=False,
        loader=FileSystemLoader(os.path.join(PATH, 'templates')),
        trim_blocks=False)

    dockerfile = os.path.join(docker_dir, 'Dockerfile')
    ctxt = {'dist': dist, 'release': release, 'http_proxy': proxy, 'https_proxy': proxy,
            'maintainer': 'dbuild, dbuild@test.com'}

    # Write Dockerfile under docker_dir
    with open(dockerfile, 'w') as d:
        dockerdata = TMPL_ENV.get_template('dockerfile.jinja').render(ctxt)
        d.write(dockerdata)
    # Copy scripts under docker_dir
    shutil.copytree(os.path.join(PATH, 'scripts'),
                    os.path.join(docker_dir, 'scripts'))


def docker_build(build_dir, build_type, source_dir='source', force_rm=False,
                 docker_url='unix://var/run/docker.sock', dist='ubuntu',
                 release='trusty', extra_repos_file='repos',
                 extra_repo_keys_file='keys', build_cache=True, proxy="",
                 build_owner=None, parallel=1, no_default_sources=False,
                 include_timestamps=True, **kwargs):
    """
    build_dir:  build directory, this directory will be mounted to /build in
                container
    build_type: Type of builds, - source or binary
    source_dir: a relative path to the subdirectory of build_dir in which the
                source code is kept
    force_rm:   If True, remove the container even on build failure, if not
                container will be kep in case of build failure
    docker_url: Docker url
    dist:       Linux distribution (ubuntu or debian)
    release:    Release name of distribution
    extra_repos_file: Relative path from build_dir to a file which contain any
                        extra repo source file, which is in the format of apt
                        sources.list.
    extra_repo_keys_file: a file which contain any apt keys required for extra
                          repos. It is a relative path from build_dir
    build_cache:    Whether to use docker build cache or not
    proxy:          value of proxy to be passed when used behind proxy settings
                    otherwise it will be default empty
    build_owner:    user id which will own all build files
    parallel:       how many processes to run in parallel
    no_default_sources: only use sources from extra_repos_file
    include_timestamps: show timestamps
    kwargs:         dict of unknown arguments. Ignored. For forward compatibility.
    """

    command = ''

    if no_default_sources:
        command += '> /etc/apt/sources.list && '

    if os.path.exists(os.path.join(build_dir, extra_repos_file)):
        command += 'cp /build/%s \
        /etc/apt/sources.list.d/dbuild-extra-repos.list && ' % extra_repos_file

    if os.path.exists(os.path.join(build_dir, extra_repo_keys_file)):
        command += 'apt-key add /build/%s && ' % extra_repo_keys_file

    command += 'export DEBIAN_FRONTEND=noninteractive; apt-get -y update \
                   && apt-get -y dist-upgrade && '

    if build_type == 'source':
        command += 'dpkg-buildpackage -S -I -nc -uc -us'
        cwd = '/build/' + source_dir
    elif build_type == 'binary':
        command += "dpkg-source -x /build/*.dsc /build/pkgbuild/ && \
                      cd /build/pkgbuild && \
                      /usr/lib/pbuilder/pbuilder-satisfydepends && \
                      dpkg-buildpackage -b -uc -us -j{}".format(parallel)
        cwd = '/build'
    else:
        raise exceptions.DbuildBuildFailedException(
            'Unknown build_type: %s' % build_type)

    if build_owner:
        command += ' ; rv=$? ; chown -R %s /build ; exit $rv' % build_owner

    c = docker_client(docker_url)
    print("Starting %s Package Build" % build_type)

    # Create docker_dir - a temporary directory which will have Dockerfile and
    # scripts to build the container.
    docker_path = mkdtemp()

    try:
        create_dockerfile(dist, release, docker_path, proxy)
        image_tag = 'dbuild-' + dist + '/' + release
        for l in build_image(c, docker_path, tag=image_tag, nocache=not build_cache):
            print(l)
    finally:
        shutil.rmtree(docker_path)

    container = create_container(c, image_tag, cwd=cwd,
                                 command=['bash', '-c', command],
                                 shared_volumes={build_dir: '/build'})
    print(container)

    start_container(c, container)

    if sys.version_info.major == 2:
        stdout = codecs.getwriter('utf-8')(sys.stdout)
    else:
        stdout = sys.stdout

    for l in container_logs(c, container):
        stdout.write(l.decode('utf-8'))
        stdout.write('\n')

    rv = wait_container(c, container)

    if rv == 0:
        print('Build successful (build type: %s), removing container %s' % (
            build_type, container.get('Id')))
        remove_container(c, container, force=True)
        build_rv = True
    else:
        if force_rm:
            print("Build failed (build type: %s), Removing container %s" % (
                build_type, container.get('Id')))
            remove_container(c, container, force=True)
            build_rv = False
        else:
            print("Build failed (build type: %s), keeping container %s" % (
                build_type, container.get('Id')))
            build_rv = False

    if build_rv:
        return build_rv
    elif build_type == 'source':
        raise exceptions.DbuildSourceBuildFailedException(
            'Source build FAILED')
    elif build_type == 'binary':
        raise exceptions.DbuildBinaryBuildFailedException(
            'Binary build FAILED')


def main(argv=sys.argv[1:]):
    ap = argparse.ArgumentParser(
        description='Build debian packages in docker container')
    ap.add_argument('build_dir', type=str, help='package build directory')
    ap.add_argument('--source-dir', type=str, default='source',
                    help='subdirectory of build_dir where sources kept')
    ap.add_argument('--force-rm', action='store_true', default=False,
                    help='Remove the containers even if build failed')
    ap.add_argument('--docker-url', type=str,
                    default='unix://var/run/docker.sock',
                    help='Docker url, it can be unix socket or tcp url')
    ap.add_argument('--dist', type=str, default='ubuntu',
                    help='Linux dist to use for container to build')
    ap.add_argument('--release', type=str, default='trusty',
                    help='Linux release name')
    ap.add_argument('--extra-repos-file', type=str, default='repos',
                    help='Relative file path from build-dir which contain \
                          apt source specs which is suitable for apt \
                          sources.list file.')
    ap.add_argument('--extra-repo-keys-file', type=str, default='keys',
                    help='relative file path from build-dir which contain \
                    all keys for any extra repos.')
    ap.add_argument('--build-cache', action='store_false', default=True,
                    help='Whether to use docker build cache or not')
    ap.add_argument('--proxy', type=str, default="",
                    help='Value of proxy to be passed when used behind proxy'
                         'otherwise it will be default empty')
    ap.add_argument('--build-owner', action='store', type=int,
                    help='uid to reassign everything to')
    ap.add_argument('--parallel', '-j', action='store', type=int,
                    default=1, help='how many processes to run in parallel')
    ap.add_argument('--no-default-sources', action='store_true',
                    help='Discard existing sources, only use the ones '
                         'passed in')
    ap.add_argument('--no-include-timestamps', dest='include_timestamps',
                    action='store_false',
                    help='Don\'t include timestamps in output')
    args = ap.parse_args(argv)

    try:
        docker_build(build_dir=args.build_dir,
                     build_type='source', source_dir=args.source_dir,
                     force_rm=args.force_rm, docker_url=args.docker_url,
                     dist=args.dist, release=args.release,
                     extra_repos_file=args.extra_repos_file,
                     extra_repo_keys_file=args.extra_repo_keys_file,
                     build_cache=args.build_cache, proxy=args.proxy,
                     build_owner=args.build_owner,
                     no_default_sources=args.no_default_sources,
                     include_timestamps=args.include_timestamps)
    except exceptions.DbuildSourceBuildFailedException:
        print('ERROR | Source build failed for build directory: %s'
              % args.build_dir)
        return False

    try:
        docker_build(build_dir=args.build_dir,
                     build_type='binary', source_dir=args.source_dir,
                     force_rm=args.force_rm, docker_url=args.docker_url,
                     dist=args.dist, release=args.release,
                     extra_repos_file=args.extra_repos_file,
                     extra_repo_keys_file=args.extra_repo_keys_file,
                     build_cache=args.build_cache, proxy=args.proxy,
                     build_owner=args.build_owner,
                     parallel=args.parallel,
                     no_default_sources=args.no_default_sources,
                     include_timestamps=args.include_timestamps)
    except exceptions.DbuildBinaryBuildFailedException:
        print('ERROR | Binary build failed for build directory: %s'
              % args.build_dir)
        return False

    return True

if __name__ == "__main__":
    sys.exit(not main(sys.argv[1:]))
