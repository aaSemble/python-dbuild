import types
from unittest import TestCase

import mock

import dbuild


class DbuildTests(TestCase):
    @mock.patch('dbuild.Client')
    def test_client_connects_to_unix_socket_by_default(self, Client):
        connection = dbuild.docker_client()
        Client.assert_called_with('unix://var/run/docker.sock')
        self.assertEquals(Client.return_value, connection)

    def test_build_image(self):
        docker_client = mock.MagicMock()

        docker_client.build.return_value = iter([{'stream': 'line1'},
                                                 {'stream': 'line2'},
                                                 {'stream': 'line3'},
                                                 {'error': 'some error occurred',
                                                  'errorDetails': 'more details'}])

        rv = dbuild.build_image(docker_client, 'some/path', 'sometag', False)

        self.assertEquals(type(rv), types.GeneratorType)

        expected_values = ['line3', 'line2', 'line1']

        for line in rv:
            self.assertEquals(expected_values.pop(), line)
            if not expected_values:
                break

        with self.assertRaises(dbuild.exceptions.DbuildDockerBuildFailedException):
            for line in rv:
                assert False, 'returned more lines before raising exception'

        docker_client.build.assert_called_with(path='some/path', rm=True, forcerm=True,
                                               tag='sometag', decode=True, nocache=False)

    def test_create_container_defaults(self):
        docker_client = mock.MagicMock()
        dbuild.create_container(docker_client, 'imagename')
        docker_client.create_container.assert_called_with(image='imagename', name=None,
                                                          command=None, environment=None,
                                                          network_disabled=False, volumes=None,
                                                          working_dir=None, host_config=None)

    def test_create_container_shared_volumes(self):
        docker_client = mock.MagicMock()
        dbuild.create_container(docker_client, 'imagename', shared_volumes={'/something': '/else'})

        docker_client.create_host_config.assert_called_with(binds=['/something:/else'])

        host_config = docker_client.create_host_config.return_value
        docker_client.create_container.assert_called_with(image='imagename', name=None,
                                                          command=None, environment=None,
                                                          network_disabled=False, volumes=['/else'],
                                                          working_dir=None, host_config=host_config)
