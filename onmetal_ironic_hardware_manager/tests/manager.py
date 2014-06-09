# Copyright 2014 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock
import os
import six

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent import utils
from oslotest import base as test_base

import onmetal_ironic_hardware_manager as onmetal_hardware_manager

if six.PY2:
    OPEN_FUNCTION_NAME = '__builtin__.open'
else:
    OPEN_FUNCTION_NAME = 'builtins.open'

DDCLI_LISTALL_OUT = (
    '\n'
    '*************************************************************************'
        '***\n'
    '   LSI Corporation WarpDrive Management Utility\n'
    '   Version 112.00.01.00 (2014.03.04)\n'
    '   Copyright (c) 2014 LSI Corporation. All Rights Reserved.\n'
    '*************************************************************************'
        '***\n'
    '\n'
    'ID    WarpDrive     Package Version    PCI Address\n'
    '--    ---------     ---------------    -----------\n'
    '1     NWD-BLP4-1600      11.00.00.00        00:02:00:00\n'
    '2     NWD-BLP4-1600      11.00.00.00        00:04:00:00\n'
    '\n'
    'LSI WarpDrive Management Utility: Execution completed successfully.\n'
)

DDCLI_FORMAT_OUT = (
    '\n'
    '*************************************************************************'
        '***\n'
    '   LSI Corporation WarpDrive Management Utility\n'
    '   Version 112.00.01.00 (2014.03.04)\n'
    '   Copyright (c) 2014 LSI Corporation. All Rights Reserved.\n'
    '*************************************************************************'
        '***\n'
    'LSI WarpDrive Management Utility: Preparing WarpDrive for format.\n'
    'LSI WarpDrive Management Utility: Please wait. Format of WarpDrive is in '
        'progress.....\n'
    'LSI WarpDrive Management Utility: WarpDrive format successfully '
        'completed.\n'
    '\n'
    'LSI WarpDrive Management Utility: Execution completed successfully.\n'
)


class TestOnMetalHardwareManager(test_base.BaseTestCase):
    def setUp(self):
        super(TestOnMetalHardwareManager, self).setUp()
        self.hardware = onmetal_hardware_manager.OnMetalHardwareManager()

    def _mock_file(self, mocked_open, contents):
        mocked_open.return_value.__enter__ = lambda s: s
        mocked_open.return_value.__exit__ = mock.Mock()
        read_mock = mocked_open.return_value.read
        read_mock.return_value = contents

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_erase_block_device_lsi_success(self,
                                            mocked_open,
                                            mocked_execute,
                                            mocked_realpath):
        block_device = hardware.BlockDevice('/dev/sda', 1073741824)

        # Mock out the model detection
        self._mock_file(mocked_open, 'NWD-BLP4-1600\n')

        # Mock the PCI address lookup
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        mocked_execute.side_effect = [
            (DDCLI_LISTALL_OUT, ''),
            (DDCLI_FORMAT_OUT, ''),
        ]
        self.hardware.erase_block_device(block_device)

        mocked_execute.assert_has_calls([
            mock.call('ddcli', '-listall'),
            mock.call('ddcli', '-c', '1', '-format', '-s'),
        ])

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_erase_block_device_lsi_notfound(self,
                                             mocked_open,
                                             mocked_execute,
                                             mocked_realpath):
        block_device = hardware.BlockDevice('/dev/sda', 1073741824)
        self._mock_file(mocked_open, 'NWD-BLP4-1600\n')

        # The '0000:06:00.0' does not map to an address in the ddcli output
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:06:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        mocked_execute.side_effect = [
            (DDCLI_LISTALL_OUT, ''),
        ]

        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

        mocked_execute.assert_has_calls([
            mock.call('ddcli', '-listall'),
        ])

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_erase_block_device_lsi_multiple(self,
                                             mocked_open,
                                             mocked_execute,
                                             mocked_realpath):
        block_device = hardware.BlockDevice('/dev/sda', 1073741824)
        self._mock_file(mocked_open, 'NWD-BLP4-1600\n')
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        # Perhaps ddcli returns the same address twice for some reason
        duplicate_output = DDCLI_LISTALL_OUT.replace('00:04:00:00',
                                                     '00:02:00:00')

        mocked_execute.side_effect = [
            (duplicate_output, ''),
        ]

        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

        mocked_execute.assert_has_calls([
            mock.call('ddcli', '-listall'),
        ])

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_erase_block_device_lsi_error(self,
                                          mocked_open,
                                          mocked_execute,
                                          mocked_realpath):
        block_device = hardware.BlockDevice('/dev/sda', 1073741824)
        self._mock_file(mocked_open, 'NWD-BLP4-1600\n')
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        # Presumably it doesn't print success on an error
        error_output = DDCLI_LISTALL_OUT.replace(
            'WarpDrive format successfully completed.',
            'Something went terribly, terribly wrong.')

        mocked_execute.side_effect = [
            (DDCLI_LISTALL_OUT, ''),
            (error_output, ''),
        ]

        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

        mocked_execute.assert_has_calls([
            mock.call('ddcli', '-listall'),
            mock.call('ddcli', '-c', '1', '-format', '-s'),
        ])

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '.erase_block_device')
    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_erase_block_device_defer_to_generic(self,
                                                 mocked_open,
                                                 mocked_execute,
                                                 mocked_realpath,
                                                 mocked_generic_erase):
        self._mock_file(mocked_open, 'Some Other Thing\n')
        block_device = hardware.BlockDevice('/dev/sda', 1073741824)
        self.hardware.erase_block_device(block_device)
        mocked_generic_erase.assert_called_once_with(block_device)
        mocked_execute.assert_has_calls([])
