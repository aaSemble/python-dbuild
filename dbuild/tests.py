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

    def test_start_container(self):
        docker_client = mock.MagicMock()
        container = {'Id': 1234}

        dbuild.start_container(docker_client, container)

        docker_client.start.assert_called_with(container=1234)

    def test_wait_container(self):
        docker_client = mock.MagicMock()

        dbuild.wait_container(docker_client, 1234)

        docker_client.wait.assert_called_with(container=1234)

    def test_container_logs(self):
        docker_client = mock.MagicMock()
        docker_client.logs.return_value = iter(['line1', 'line2', 'line3'])

        rv = dbuild.container_logs(docker_client, 1234)

        self.assertEquals(type(rv), types.GeneratorType)
        self.assertEquals(list(rv), ['line1', 'line2', 'line3'])

        docker_client.logs.assert_called_with(container=1234, stream=True, timestamps=True)
